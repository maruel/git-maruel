#!/usr/bin/env python3
"""Integration tests for git-rb."""

import pathlib
import platform
import subprocess
import tempfile
import unittest

_SCRIPT = pathlib.Path(__file__).resolve().parent.parent / "git-rb"


class TestRebase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = pathlib.Path(self.tmp.name)
        self.git("init", "--initial-branch=main")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test User")
        self.git("config", "core.hooksPath", ".git/no-hooks")
        self.commit_file("tracked.txt", "base\n")

    def git(self, *args: str) -> str:
        return subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, check=True).stdout.strip()

    def commit_file(self, name: str, content: str):
        (self.repo / name).write_text(content, encoding="utf-8")
        self.git("add", name)
        self.git("commit", "-m", f"Update {name}")

    def branch(self, name: str, parent: str = "main"):
        self.git("switch", "--create", name, parent)
        self.git("branch", "--set-upstream-to", parent)

    def run_rb(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [_SCRIPT],
            cwd=self.repo,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    def test_conflicts_continue_cleanup_and_checkout_first_failure(self):
        failed_tips = {}
        for name in ("a_conflict", "c_conflict"):
            self.branch(name)
            self.commit_file("tracked.txt", f"{name}\n")
            failed_tips[name] = self.git("rev-parse", "HEAD")
        self.branch("b_success")
        self.commit_file("success.txt", "success\n")
        success_tip = self.git("rev-parse", "HEAD")
        self.branch("d_empty")
        self.branch("e_child", "a_conflict")
        self.commit_file("child.txt", "child\n")
        self.git("switch", "main")
        self.commit_file("tracked.txt", "upstream\n")
        main_tip = self.git("rev-parse", "HEAD")

        result = self.run_rb()

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.git("branch", "--show-current"), "a_conflict")
        self.assertEqual(result.stderr, "")
        self.assertNotIn("CONFLICT", result.stdout)
        for name, tip in failed_tips.items():
            self.assertEqual(self.git("rev-parse", name), tip)
            status = "conflicted"
            branch = name
            if platform.system() != "Windows":
                status = f"\033[31m{status}\033[0m"
                branch = f"\033[1m{name}\033[0m"
            line = f"- {branch}: {status}"
            self.assertIn(line, result.stdout.splitlines())
            self.assertLess(result.stdout.index(": deleted"), result.stdout.index(line))
        self.assertNotEqual(self.git("rev-parse", "b_success"), success_tip)
        self.assertEqual(self.git("merge-base", "main", "b_success"), main_tip)
        self.assertEqual(self.git("show", "b_success:success.txt"), "success")
        self.assertEqual(self.git("show", "e_child:child.txt"), "child")
        self.assertGreater(result.stdout.index("e_child"), result.stdout.index("c_conflict"))
        self.assertNotIn("d_empty", self.git("branch", "--format=%(refname:short)").splitlines())
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertFalse((self.repo / ".git/rebase-merge").exists())
        self.assertFalse((self.repo / ".git/rebase-apply").exists())

    def test_failed_abort_stops_and_preserves_dirty_worktree(self):
        self.branch("a_feature")
        self.commit_file("feature.txt", "feature\n")
        self.branch("b_later")
        self.commit_file("later.txt", "later\n")
        later_tip = self.git("rev-parse", "HEAD")
        self.git("switch", "main")
        self.commit_file("upstream.txt", "upstream\n")
        (self.repo / "tracked.txt").write_text("dirty\n", encoding="utf-8")

        result = self.run_rb()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unstaged changes", result.stderr)
        self.assertEqual(self.git("rev-parse", "b_later"), later_tip)
        self.assertNotIn("b_later", result.stdout)
        self.assertEqual((self.repo / "tracked.txt").read_text(encoding="utf-8"), "dirty\n")
        self.assertFalse((self.repo / ".git/rebase-merge").exists())
        self.assertFalse((self.repo / ".git/rebase-apply").exists())

    def test_signing_failure_reports_diagnostics_and_aborts(self):
        self.branch("feature")
        self.commit_file("feature.txt", "feature\n")
        feature_tip = self.git("rev-parse", "HEAD")
        self.git("switch", "main")
        self.commit_file("upstream.txt", "upstream\n")
        self.git("config", "commit.gpgsign", "true")
        self.git("config", "gpg.format", "openpgp")
        self.git("config", "gpg.program", "false")

        result = self.run_rb()

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("failed to sign", result.stderr)
        status = "rebase failed"
        branch = "feature"
        if platform.system() != "Windows":
            status = f"\033[31m{status}\033[0m"
            branch = "\033[1mfeature\033[0m"
        self.assertIn(f"- {branch}: {status}", result.stdout.splitlines())
        self.assertNotIn("conflicted", result.stdout)
        self.assertEqual(self.git("rev-parse", "feature"), feature_tip)
        self.assertEqual(self.git("branch", "--show-current"), "feature")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertFalse((self.repo / ".git/rebase-merge").exists())
        self.assertFalse((self.repo / ".git/rebase-apply").exists())

    def test_success_restores_original_branch(self):
        self.branch("feature")
        self.commit_file("feature.txt", "feature\n")
        self.git("switch", "main")
        self.commit_file("upstream.txt", "upstream\n")
        self.git("switch", "feature")

        result = self.run_rb()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("branch", "--show-current"), "feature")
        self.assertEqual(self.git("show", "HEAD:upstream.txt"), "upstream")

    def test_deleted_original_branch_falls_back_and_reparents_child(self):
        self.branch("empty")
        self.branch("child", "empty")
        self.commit_file("child.txt", "child\n")
        self.git("switch", "empty")

        result = self.run_rb()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git("branch", "--show-current"), "main")
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "child@{upstream}"), "main")
        self.assertNotIn("empty", self.git("branch", "--format=%(refname:short)").splitlines())


if __name__ == "__main__":
    unittest.main()
