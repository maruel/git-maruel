#!/usr/bin/env python3
"""Tests for git-desc."""

import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import threading
import unittest
from unittest import mock

# Import git-desc as a module despite the hyphen and missing .py extension.
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_loader = importlib.machinery.SourceFileLoader(
    "git_desc", os.path.join(_HERE, "git-desc")
)
_spec = importlib.util.spec_from_loader("git_desc", _loader)
gd = importlib.util.module_from_spec(_spec)
_loader.exec_module(gd)


def _diff(path, body, extra=""):
    """Return git diff output for one file with one hunk."""
    return (
        f"diff --git a/{path} b/{path}\n"
        f"{extra}"
        "index 1111111..2222222 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        "@@ -1,2 +1,2 @@ func\n"
        f"{body}"
    )


def _file(path, lines, context=0):
    """Return a FileDiff with one hunk of added lines surrounded by context."""
    ctx = tuple(f" ctx{i}\n" for i in range(context))
    body = ctx + tuple(lines) + ctx
    return gd.FileDiff(
        path, f"diff --git a/{path} b/{path}\n", (gd.Hunk(1, 1, "", body),)
    )


class TestParseDiff(unittest.TestCase):
    def test_preamble_and_file(self):
        preamble, files = gd.parse_diff(
            "commit abc\n\n    Subject\n\n" + _diff("a.go", " x\n-old\n+new\n")
        )
        self.assertEqual(preamble, "commit abc\n\n    Subject")
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].path, "a.go")
        self.assertEqual(files[0].hunks[0].section, " func")

    def test_render_drops_index_and_file_lines(self):
        _, files = gd.parse_diff(_diff("a.go", " x\n-old\n+new\n"))
        self.assertEqual(
            files[0].render(),
            "diff --git a/a.go b/a.go\n@@ -1,2 +1,2 @@ func\n x\n-old\n+new\n",
        )

    def test_deleted_file_omitted(self):
        _, files = gd.parse_diff(
            _diff("a.go", "-old\n", extra="deleted file mode 100644\n")
        )
        self.assertEqual(
            files[0].render(),
            "diff --git a/a.go b/a.go\ndeleted file mode 100644\n(content omitted)\n",
        )

    def test_lock_files_omitted(self):
        for path in ("go.sum", "sub/Cargo.lock", "package-lock.json"):
            _, files = gd.parse_diff(_diff(path, "+x\n"))
            self.assertTrue(files[0].omitted, path)

    def test_long_line_truncated(self):
        _, files = gd.parse_diff(_diff("a.go", "+" + "x" * 5000 + "\n"))
        line = files[0].hunks[0].lines[0]
        self.assertEqual(len(line), gd._MAX_LINE + len(" [truncated]\n"))

    def test_missing_final_newline(self):
        _, files = gd.parse_diff(_diff("a.go", "-old\n+new"))
        self.assertEqual(files[0].hunks[0].lines, ("-old\n", "+new\n"))

    def test_multiple_files(self):
        _, files = gd.parse_diff(_diff("a.go", "+a\n") + _diff("b.go", "+b\n"))
        self.assertEqual([f.path for f in files], ["a.go", "b.go"])

    def test_noprefix_path(self):
        _, files = gd.parse_diff("diff --git a.go a.go\n@@ -1 +1 @@\n+x\n")
        self.assertEqual(files[0].path, "a.go")

    def test_path_containing_diff_separator(self):
        _, files = gd.parse_diff(_diff("lib b/name.go", "+x\n"))
        self.assertEqual(files[0].path, "lib b/name.go")

    def test_binary_path_containing_diff_separator(self):
        _, files = gd.parse_diff(
            "diff --git a/lib b/name.bin b/lib b/name.bin\n"
            "Binary files a/lib b/name.bin and b/lib b/name.bin differ\n"
        )
        self.assertEqual(files[0].path, "lib b/name.bin")

    def test_quoted_path(self):
        text = (
            'diff --git "a/caf\\303\\251.go" "b/caf\\303\\251.go"\n'
            '--- "a/caf\\303\\251.go"\n'
            '+++ "b/caf\\303\\251.go"\n'
            "@@ -1 +1 @@\n+x\n"
        )
        _, files = gd.parse_diff(text)
        self.assertEqual(files[0].path, "café.go")

    def test_malformed_hunk_header(self):
        with self.assertRaises(gd.Error):
            gd.parse_diff("diff --git a/a b/a\n@@ bogus\n")


class TestFileClassification(unittest.TestCase):
    def test_test_file(self):
        self.assertTrue(gd._is_test_file("pkg/foo_test.go"))
        self.assertTrue(gd._is_test_file("test_foo.py"))
        self.assertFalse(gd._is_test_file("pkg/foo.go"))
        self.assertFalse(gd._is_test_file("testdata/helper.go"))

    def test_data_file(self):
        self.assertTrue(gd._is_data_file("foo.json"))
        self.assertTrue(gd._is_data_file("foo.yaml"))
        self.assertTrue(gd._is_data_file("foo.yml"))
        self.assertFalse(gd._is_data_file("foo.go"))


class TestHunkWithContext(unittest.TestCase):
    def _trim(self, lines, n):
        return gd.Hunk(10, 20, "", tuple(lines)).with_context(n)

    def test_no_context(self):
        body = ["-old\n", "+new\n"]
        self.assertEqual(self._trim(body, 3).lines, tuple(body))

    def test_leading_trimmed(self):
        hunk = self._trim([" a\n", " b\n", " c\n", " d\n", " e\n", "-old\n"], 2)
        self.assertEqual(hunk.lines, (" d\n", " e\n", "-old\n"))
        self.assertEqual((hunk.old_start, hunk.new_start), (13, 23))

    def test_trailing_trimmed(self):
        hunk = self._trim(["-old\n", " a\n", " b\n", " c\n", " d\n"], 2)
        self.assertEqual(hunk.lines, ("-old\n", " a\n", " b\n"))
        self.assertEqual((hunk.old_start, hunk.new_start), (10, 20))

    def test_middle_trimmed(self):
        middle = [f" m{i}\n" for i in range(10)]
        hunk = self._trim(["-old1\n", *middle, "-old2\n"], 2)
        self.assertEqual(
            hunk.lines, ("-old1\n", " m0\n", " m1\n", " m8\n", " m9\n", "-old2\n")
        )

    def test_short_middle_kept(self):
        body = ["-old1\n", " m0\n", " m1\n", " m2\n", "-old2\n"]
        self.assertEqual(self._trim(body, 2).lines, tuple(body))

    def test_zero_context(self):
        hunk = self._trim([" a\n", "-old\n", " b\n", "+new\n", " c\n"], 0)
        self.assertEqual(hunk.lines, ("-old\n", "+new\n"))
        self.assertEqual(hunk.header(), "@@ -11,1 +21,1 @@\n")

    def test_no_newline_marker_kept(self):
        body = ["-old\n", "+new\n", "\\ No newline at end of file\n"]
        self.assertEqual(self._trim(body, 3).lines, tuple(body))


class TestHunkSplit(unittest.TestCase):
    def test_split(self):
        lines = tuple(f"+line{i:03}\n" for i in range(100))
        hunks = gd.Hunk(1, 1, " func", lines).split(200)
        self.assertGreater(len(hunks), 1)
        for hunk in hunks:
            self.assertLessEqual(len(hunk.render()), 200)
        self.assertEqual(tuple(l for h in hunks for l in h.lines), lines)
        self.assertEqual(hunks[1].old_start, 1)
        self.assertEqual(hunks[1].new_start, 1 + len(hunks[0].lines))


class TestPack(unittest.TestCase):
    def test_fits(self):
        self.assertEqual(gd.pack(["a", "b"], 10), [["a", "b"]])

    def test_balanced(self):
        groups = gd.pack(["x" * 10] * 18, 100)
        self.assertEqual([len(g) for g in groups], [9, 9])

    def test_oversized_item_alone(self):
        items = ["a" * 5, "b" * 50, "c" * 5]
        self.assertEqual(gd.pack(items, 20), [[items[0]], [items[1]], [items[2]]])

    def test_empty(self):
        self.assertEqual(gd.pack([], 10), [])


class TestSplitDiff(unittest.TestCase):
    def test_small_files_grouped(self):
        files = [_file("a.go", ["+a\n"]), _file("b.go", ["+b\n"])]
        self.assertEqual(
            gd.split_diff(files, 1000), ["".join(f.render() for f in files)]
        )

    def test_large_file_split_with_header(self):
        f = _file("big.go", [f"+line{i:04}\n" for i in range(500)])
        parts = gd.split_diff([f], 1000)
        self.assertGreater(len(parts), 1)
        for part in parts:
            self.assertLessEqual(len(part), 1000)
            self.assertTrue(part.startswith(f.header))
        text = "".join(parts)
        for line in f.hunks[0].lines:
            self.assertIn(line, text)


class TestReduceDiff(unittest.TestCase):
    def test_stops_when_it_fits(self):
        files = [_file("a.go", ["+a\n"], context=10), _file("a_test.go", ["+t\n"])]
        reduced = gd.reduce_diff(files, 200)
        self.assertLessEqual(sum(len(f.render()) for f in reduced), 200)
        self.assertEqual(len(reduced[0].hunks[0].lines), 7)
        self.assertFalse(reduced[1].omitted)

    def test_omits_tests_then_data(self):
        files = [
            _file("a.go", ["+a\n"], context=10),
            _file("a_test.go", ["+t\n"]),
            _file("c.yaml", ["+c\n"]),
        ]
        reduced = gd.reduce_diff(files, 0)
        self.assertEqual([f.omitted for f in reduced], [False, True, True])


class _FakeAsk:
    """Records requests and answers with reply(prompt, data)."""

    def __init__(self, reply):
        self.reply = reply
        self.calls = []
        self._lock = threading.Lock()

    def __call__(self, prompt, data):
        with self._lock:
            self.calls.append((prompt, data))
        return self.reply(prompt, data)

    def prompts(self):
        return [prompt for prompt, _ in self.calls]


_PROMPTS = gd.Prompts(whole="WHOLE", part="PART", final="FINAL")
_BUDGET = 20_000


def _source(files, context="=== Branch ===\nfeature\n\n"):
    return gd.Source(context=context, brief=context, files=files)


def _big_files(count=10):
    return [
        _file(f"f{i}.go", [f"+{i} line{j:03}\n" for j in range(400)])
        for i in range(count)
    ]


class TestDescribe(unittest.TestCase):
    def test_whole(self):
        ask = _FakeAsk(lambda prompt, data: "message")
        result = gd.describe(_source([_file("a.go", ["+a\n"])]), _PROMPTS, _BUDGET, ask)
        self.assertEqual(result, "message")
        self.assertEqual(ask.prompts(), ["WHOLE"])
        self.assertIn("=== Branch ===", ask.calls[0][1])
        self.assertIn("+a\n", ask.calls[0][1])

    def test_split(self):
        files = _big_files()
        ask = _FakeAsk(lambda prompt, data: "final" if prompt == "FINAL" else "summary")
        result = gd.describe(_source(files), _PROMPTS, _BUDGET, ask)
        self.assertEqual(result, "final")
        prompts = ask.prompts()
        self.assertGreater(prompts.count("PART"), 1)
        self.assertEqual(prompts[-1], "FINAL")
        for _, data in ask.calls:
            self.assertLessEqual(len(data), _BUDGET)
        parts = "".join(data for prompt, data in ask.calls if prompt == "PART")
        for f in files:
            self.assertIn(f.hunks[0].lines[-1], parts)
        self.assertIn("=== Part summaries ===\nsummary", ask.calls[-1][1])

    def test_merges_long_summaries(self):
        replies = {"PART": "s" * 8000, gd._MERGE_PROMPT: "merged", "FINAL": "final"}
        ask = _FakeAsk(lambda prompt, data: replies[prompt])
        result = gd.describe(_source(_big_files()), _PROMPTS, _BUDGET, ask)
        self.assertEqual(result, "final")
        self.assertIn(gd._MERGE_PROMPT, ask.prompts())
        for _, data in ask.calls:
            self.assertLessEqual(len(data), _BUDGET)

    def test_splits_one_oversized_summary_before_merging(self):
        replies = {
            "PART": "summary " * 4000,
            gd._MERGE_PROMPT: "merged",
            "FINAL": "final",
        }
        ask = _FakeAsk(lambda prompt, data: replies[prompt])
        result = gd.describe(_source(_big_files()), _PROMPTS, _BUDGET, ask)
        self.assertEqual(result, "final")
        self.assertIn(gd._MERGE_PROMPT, ask.prompts())
        for _, data in ask.calls:
            self.assertLessEqual(len(data), _BUDGET)

    def test_merge_without_progress(self):
        ask = _FakeAsk(lambda prompt, data: "s" * 30_000)
        with self.assertRaises(gd.Error):
            gd.describe(_source(_big_files()), _PROMPTS, _BUDGET, ask)

    def test_ask_error(self):
        def reply(prompt, data):
            raise gd.Error("boom")

        with self.assertRaisesRegex(gd.Error, "boom"):
            gd.describe(_source(_big_files()), _PROMPTS, _BUDGET, _FakeAsk(reply))

    def test_no_changes(self):
        with self.assertRaises(gd.Error):
            gd.describe(_source([]), _PROMPTS, _BUDGET, _FakeAsk(None))

    def test_metadata_too_large(self):
        source = _source([_file("a.go", ["+a\n"])], context="x" * _BUDGET)
        with self.assertRaises(gd.Error):
            gd.describe(source, _PROMPTS, _BUDGET, _FakeAsk(None))


class TestStdinSource(unittest.TestCase):
    def test_header_and_excludes(self):
        text = "commit abc\n\n" + _diff("a.go", "+a\n") + _diff("vendor/b.go", "+b\n")
        source = gd.stdin_source(text, ["vendor/"])
        self.assertEqual(source.context, "=== Input header ===\ncommit abc\n\n")
        self.assertEqual([f.path for f in source.files], ["a.go"])


class TestGitSource(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        env = mock.patch.dict(
            os.environ,
            {
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@example.com",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1",
            },
        )
        env.start()
        self.addCleanup(env.stop)
        cwd = os.getcwd()
        os.chdir(tmp.name)
        self.addCleanup(os.chdir, cwd)
        self._git("init", "-q", "-b", "main")
        self._commit("a.go", "one\n", "Upstream subject")
        self._git("checkout", "-q", "-b", "feature", "--track", "main")
        os.mkdir("vendor")
        self._commit("vendor/v.go", "vendored\n", "Add vendor")
        self._commit("a.go", "two\n", "Feature subject\n\nFeature body")

    def _git(self, *args):
        subprocess.run(["git", *args], check=True, capture_output=True)

    def _commit(self, path, content, message):
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self._git("add", path)
        self._git("commit", "-q", "-m", message)

    def test_commit(self):
        self._git("config", "color.ui", "always")
        self._git("config", "core.quotePath", "false")
        self._git("config", "diff.mnemonicPrefix", "true")
        self._git("config", "diff.noprefix", "true")
        self._git("config", "diff.relative", "true")
        source = gd.git_source(None, False, ["vendor/"])
        self.assertEqual([f.path for f in source.files], ["a.go"])
        self.assertTrue(source.files[0].render().startswith("diff --git a/a.go b/a.go"))
        self.assertNotIn("\x1b", source.context)
        self.assertIn("=== Branch ===\nfeature\n", source.context)
        self.assertIn("Upstream subject", source.context)
        self.assertNotIn("Upstream subject", source.brief)
        self.assertNotIn("v.go", source.context)

    def test_release(self):
        source = gd.git_source("main", True, [])
        self.assertEqual([f.path for f in source.files], ["a.go", "vendor/v.go"])
        self.assertIn("Feature body", source.context)
        self.assertNotIn("Feature body", source.brief)
        self.assertIn("Feature subject", source.brief)


if __name__ == "__main__":
    unittest.main()
