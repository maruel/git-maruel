#!/usr/bin/env python3
"""Tests for git-squash."""

import pathlib
import subprocess
import tempfile
import unittest

_HERE = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _HERE / "git-squash"


class TestSquash(unittest.TestCase):
    def test_preserves_worktree_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp)
            tracked = self._create_feature(repo, commits=2)
            tracked.write_text("unstaged\n", encoding="utf-8")
            untracked = repo / "untracked.txt"
            untracked.write_text("preserved\n", encoding="utf-8")

            result = subprocess.run(
                [_SCRIPT], cwd=repo, capture_output=True, text=True, check=False
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(tracked.read_text(encoding="utf-8"), "unstaged\n")
            self.assertEqual(untracked.read_text(encoding="utf-8"), "preserved\n")
            self.assertEqual(
                self._git(repo, "rev-list", "--count", "main..HEAD").stdout,
                "1\n",
            )

    def test_failed_commit_preserves_hook_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = pathlib.Path(tmp)
            tracked = self._create_feature(repo, commits=2)
            original_head = self._git(repo, "rev-parse", "HEAD").stdout.strip()
            hooks = repo / ".git" / "no-hooks"
            hooks.mkdir()
            hook = hooks / "pre-commit"
            hook.write_text(
                "#!/bin/sh\nprintf 'hook change\\n' >tracked.txt\nexit 1\n",
                encoding="utf-8",
            )
            hook.chmod(0o755)

            result = subprocess.run(
                [_SCRIPT], cwd=repo, capture_output=True, text=True, check=False
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(
                self._git(repo, "rev-parse", "HEAD").stdout.strip(), original_head
            )
            self.assertEqual(tracked.read_text(encoding="utf-8"), "hook change\n")
            self.assertEqual(
                self._git(repo, "status", "--short").stdout, " M tracked.txt\n"
            )

    def _create_feature(self, repo: pathlib.Path, commits: int = 1) -> pathlib.Path:
        repo.mkdir(exist_ok=True)
        self._git(repo, "init", "--initial-branch=main")
        self._git(repo, "config", "user.email", "test@example.com")
        self._git(repo, "config", "user.name", "Test User")
        self._git(repo, "config", "core.hooksPath", ".git/no-hooks")

        tracked = repo / "tracked.txt"
        tracked.write_text("base\n", encoding="utf-8")
        self._git(repo, "add", "tracked.txt")
        self._git(repo, "commit", "-m", "Initial commit")
        self._git(repo, "switch", "--create", "feature")
        self._git(repo, "branch", "--set-upstream-to=main")

        for number in range(commits):
            tracked.write_text(f"committed {number}\n", encoding="utf-8")
            self._git(repo, "commit", "--all", "-m", f"Feature change {number}")
        return tracked

    @staticmethod
    def _git(repo: pathlib.Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            capture_output=True,
            text=True,
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
