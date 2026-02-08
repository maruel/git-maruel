#!/usr/bin/env python3
"""Tests for git-desc."""

import importlib.machinery
import importlib.util
import os
import unittest

# Import git-desc as a module despite the hyphen and missing .py extension.
_HERE = os.path.dirname(os.path.abspath(__file__))
_loader = importlib.machinery.SourceFileLoader(
    "git_desc", os.path.join(_HERE, "git-desc")
)
_spec = importlib.util.spec_from_loader("git_desc", _loader)
gd = importlib.util.module_from_spec(_spec)
_loader.exec_module(gd)


_DIFF_A = (
    "diff --git a/foo.go b/foo.go\n"
    "--- a/foo.go\n"
    "+++ b/foo.go\n"
    "@@ -1,3 +1,3 @@\n"
    "-old\n"
    "+new\n"
)

_DIFF_TEST = (
    "diff --git a/foo_test.go b/foo_test.go\n"
    "--- a/foo_test.go\n"
    "+++ b/foo_test.go\n"
    "@@ -1,3 +1,3 @@\n"
    "-old test\n"
    "+new test\n"
)

_DIFF_JSON = (
    "diff --git a/data.json b/data.json\n"
    "--- a/data.json\n"
    "+++ b/data.json\n"
    "@@ -1,3 +1,3 @@\n"
    '-{"a":1}\n'
    '+{"a":2}\n'
)

_DIFF_YAML = (
    "diff --git a/config.yaml b/config.yaml\n"
    "--- a/config.yaml\n"
    "+++ b/config.yaml\n"
    "@@ -1,3 +1,3 @@\n"
    "-key: old\n"
    "+key: new\n"
)

_DIFF_ALL = _DIFF_A + _DIFF_TEST + _DIFF_JSON + _DIFF_YAML


class TestFilterDiff(unittest.TestCase):
    """Tests for _filter_diff and filter_diff."""

    def test_filter_by_prefix(self):
        result = gd.filter_diff(_DIFF_ALL, ["data.json"])
        self.assertIn("foo.go", result)
        self.assertIn("foo_test.go", result)
        self.assertNotIn("data.json", result)
        self.assertIn("config.yaml", result)

    def test_filter_test_files(self):
        result = gd._filter_diff(_DIFF_ALL, gd._is_test_file)
        self.assertIn("foo.go", result)
        self.assertNotIn("foo_test.go", result)
        self.assertIn("data.json", result)

    def test_filter_data_files(self):
        result = gd._filter_diff(_DIFF_ALL, gd._is_data_file)
        self.assertIn("foo.go", result)
        self.assertIn("foo_test.go", result)
        self.assertNotIn("data.json", result)
        self.assertNotIn("config.yaml", result)

    def test_filter_empty_excludes(self):
        result = gd.filter_diff(_DIFF_ALL, [])
        self.assertEqual(result, _DIFF_ALL)


class TestIsTestFile(unittest.TestCase):
    """Tests for _is_test_file."""

    def test_go_test(self):
        self.assertTrue(gd._is_test_file("pkg/foo_test.go"))

    def test_python_test(self):
        self.assertTrue(gd._is_test_file("test_foo.py"))

    def test_normal_file(self):
        self.assertFalse(gd._is_test_file("pkg/foo.go"))

    def test_test_directory(self):
        # basename is "helper.go", not a test file.
        self.assertFalse(gd._is_test_file("testdata/helper.go"))


class TestIsDataFile(unittest.TestCase):
    """Tests for _is_data_file."""

    def test_json(self):
        self.assertTrue(gd._is_data_file("foo.json"))

    def test_yaml(self):
        self.assertTrue(gd._is_data_file("foo.yaml"))

    def test_yml(self):
        self.assertTrue(gd._is_data_file("foo.yml"))

    def test_go(self):
        self.assertFalse(gd._is_data_file("foo.go"))


class TestSplitDiff(unittest.TestCase):
    """Tests for _split_diff."""

    def test_single_chunk(self):
        chunks = gd._split_diff(_DIFF_ALL, 100_000)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], _DIFF_ALL)

    def test_multiple_chunks(self):
        # Force each file into its own chunk by setting max_chunk tiny.
        chunks = gd._split_diff(_DIFF_ALL, 1)
        self.assertEqual(len(chunks), 4)
        self.assertIn("foo.go", chunks[0])
        self.assertIn("foo_test.go", chunks[1])

    def test_empty_diff(self):
        chunks = gd._split_diff("", 100)
        self.assertEqual(len(chunks), 1)

    def test_grouping(self):
        # Two small diffs should be grouped together.
        two = _DIFF_A + _DIFF_TEST
        chunks = gd._split_diff(two, len(two) + 10)
        self.assertEqual(len(chunks), 1)


class TestBuildContext(unittest.TestCase):
    """Tests for _build_context."""

    def test_with_metadata(self):
        ctx = gd._build_context("meta\n", "diff")
        self.assertEqual(ctx, "meta\n=== Changes ===\ndiff")

    def test_without_metadata(self):
        ctx = gd._build_context("", "diff")
        self.assertEqual(ctx, "=== Changes ===\ndiff")


class TestExtractPath(unittest.TestCase):
    """Tests for _extract_path."""

    def test_standard_prefix(self):
        self.assertEqual(
            gd._extract_path("diff --git a/foo.go b/foo.go"), "foo.go"
        )

    def test_noprefix(self):
        self.assertEqual(
            gd._extract_path("diff --git foo.go foo.go"), "foo.go"
        )


def _make_hunk(leading_ctx, trailing_ctx, middle_ctx=0):
    """Build a diff with configurable context line counts around a change."""
    lines = []
    lines.append("diff --git a/f.go b/f.go\n")
    lines.append("--- a/f.go\n")
    lines.append("+++ b/f.go\n")
    old_count = leading_ctx + 1 + trailing_ctx + middle_ctx
    new_count = leading_ctx + 1 + trailing_ctx + middle_ctx
    if middle_ctx:
        # Two changes with middle context between them.
        old_count += 1
        new_count += 1
    lines.append(f"@@ -1,{old_count} +1,{new_count} @@\n")
    for i in range(leading_ctx):
        lines.append(f" lead{i}\n")
    lines.append("-old\n")
    lines.append("+new\n")
    if middle_ctx:
        for i in range(middle_ctx):
            lines.append(f" mid{i}\n")
        lines.append("-old2\n")
        lines.append("+new2\n")
    for i in range(trailing_ctx):
        lines.append(f" trail{i}\n")
    return "".join(lines)


class TestTrimHunkContext(unittest.TestCase):
    """Tests for _trim_hunk_context."""

    def test_no_context(self):
        body = ["-old\n", "+new\n"]
        trimmed, lead = gd._trim_hunk_context(body, 3)
        self.assertEqual(trimmed, body)
        self.assertEqual(lead, 0)

    def test_leading_trimmed(self):
        body = [" a\n", " b\n", " c\n", " d\n", " e\n", "-old\n", "+new\n"]
        trimmed, lead = gd._trim_hunk_context(body, 2)
        self.assertEqual(lead, 3)
        self.assertEqual(trimmed, [" d\n", " e\n", "-old\n", "+new\n"])

    def test_trailing_trimmed(self):
        body = ["-old\n", "+new\n", " a\n", " b\n", " c\n", " d\n", " e\n"]
        trimmed, lead = gd._trim_hunk_context(body, 2)
        self.assertEqual(lead, 0)
        self.assertEqual(trimmed, ["-old\n", "+new\n", " a\n", " b\n"])

    def test_both_sides(self):
        body = [
            " l1\n", " l2\n", " l3\n", " l4\n",
            "-old\n", "+new\n",
            " t1\n", " t2\n", " t3\n", " t4\n",
        ]
        trimmed, lead = gd._trim_hunk_context(body, 2)
        self.assertEqual(lead, 2)
        self.assertEqual(
            trimmed,
            [" l3\n", " l4\n", "-old\n", "+new\n", " t1\n", " t2\n"],
        )

    def test_middle_context_trimmed(self):
        body = [
            "-old1\n", "+new1\n",
            " m0\n", " m1\n", " m2\n", " m3\n", " m4\n",
            " m5\n", " m6\n", " m7\n", " m8\n", " m9\n",
            "-old2\n", "+new2\n",
        ]
        trimmed, lead = gd._trim_hunk_context(body, 2)
        self.assertEqual(lead, 0)
        self.assertEqual(
            trimmed,
            [
                "-old1\n", "+new1\n",
                " m0\n", " m1\n",
                " m8\n", " m9\n",
                "-old2\n", "+new2\n",
            ],
        )

    def test_middle_context_short_kept(self):
        body = [
            "-old1\n", "+new1\n",
            " m0\n", " m1\n", " m2\n",
            "-old2\n", "+new2\n",
        ]
        trimmed, _ = gd._trim_hunk_context(body, 2)
        self.assertEqual(trimmed, body)

    def test_empty(self):
        trimmed, lead = gd._trim_hunk_context([], 3)
        self.assertEqual(trimmed, [])
        self.assertEqual(lead, 0)

    def test_no_newline_marker_kept(self):
        body = ["-old\n", "+new\n", "\\ No newline at end of file\n"]
        trimmed, _ = gd._trim_hunk_context(body, 3)
        self.assertEqual(trimmed, body)


class TestReduceDiffContext(unittest.TestCase):
    """Tests for _reduce_diff_context."""

    def test_reduces_leading_trailing(self):
        diff = _make_hunk(10, 10)
        result = gd._reduce_diff_context(diff, 3)
        # Should have 3 leading + change + 3 trailing context lines.
        hunk_lines = [
            l for l in result.splitlines()
            if l.startswith((" ", "+", "-")) and not l.startswith("+++")
            and not l.startswith("---")
        ]
        leading = [l for l in hunk_lines if l.startswith(" lead")]
        trailing = [l for l in hunk_lines if l.startswith(" trail")]
        self.assertEqual(len(leading), 3)
        self.assertEqual(len(trailing), 3)

    def test_updates_hunk_header(self):
        diff = _make_hunk(10, 10)
        result = gd._reduce_diff_context(diff, 3)
        for line in result.splitlines():
            if line.startswith("@@"):
                # old_start should be 1 + 7 = 8 (trimmed 7 leading lines).
                self.assertIn("-8,", line)
                break
        else:
            self.fail("no @@ header found")

    def test_noop_when_already_small(self):
        diff = _make_hunk(2, 2)
        result = gd._reduce_diff_context(diff, 3)
        self.assertEqual(result, diff)

    def test_middle_context_trimmed(self):
        diff = _make_hunk(3, 3, middle_ctx=20)
        result = gd._reduce_diff_context(diff, 3)
        mid_lines = [
            l for l in result.splitlines() if l.startswith(" mid")
        ]
        self.assertEqual(len(mid_lines), 6)  # 3 + 3

    def test_preserves_file_headers(self):
        diff = _make_hunk(10, 10)
        result = gd._reduce_diff_context(diff, 3)
        self.assertIn("diff --git a/f.go b/f.go", result)
        self.assertIn("--- a/f.go", result)
        self.assertIn("+++ b/f.go", result)

    def test_multiple_files(self):
        diff = _make_hunk(10, 10) + _make_hunk(10, 10)
        result = gd._reduce_diff_context(diff, 3)
        # Both files should be present and trimmed.
        self.assertEqual(result.count("diff --git"), 2)
        ctx = [
            l for l in result.splitlines()
            if l.startswith(" lead") or l.startswith(" trail")
        ]
        # 2 files * (3 lead + 3 trail) = 12.
        self.assertEqual(len(ctx), 12)

    def test_empty_diff(self):
        self.assertEqual(gd._reduce_diff_context("", 3), "")


if __name__ == "__main__":
    unittest.main()
