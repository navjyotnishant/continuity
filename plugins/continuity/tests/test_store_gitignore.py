"""tests/test_store_gitignore.py — the store's .gitignore keeps local-only files out of
`git add -A` and nothing that is project memory.

Continuity is built to ship its context with the repo, so the list is deliberately small:
raw staged notes (not yet secret-scanned), the turn marker, the lock, errors.log and temp files.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.migrate import ensure_gitignore, seed_store  # noqa: E402
from lib.write_memory import write_memory  # noqa: E402
from tests.test_write_memory_basic import stage  # noqa: E402

LOCAL_ONLY = [".staged/decision-1.md", ".turn-edited", ".lock/owner", "errors.log", "tasks.md.tmp.abc123"]
PROJECT_MEMORY = ["state.md", "tasks.md", "decisions.md", "learnings.md", "metadata.json", "sessions/20260912T140501Z-1.md", ".gitignore"]


class TestGitignoreIsSeeded(unittest.TestCase):
    def test_seed_store_writes_it_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            seed_store(store)
            path = os.path.join(store, ".gitignore")
            self.assertTrue(os.path.isfile(path))
            with open(path, "w") as handle:
                handle.write("# edited by a team\n")
            seed_store(store)
            with open(path) as handle:
                self.assertEqual(handle.read(), "# edited by a team\n")

    def test_it_lists_only_local_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".continuity"))
            ensure_gitignore(os.path.join(tmp, ".continuity"))
            with open(os.path.join(tmp, ".continuity", ".gitignore")) as handle:
                lines = [l.strip() for l in handle if l.strip() and not l.startswith("#")]
            self.assertEqual(sorted(lines), sorted(["/.staged/", "/.turn-edited", "/.lock/", "/errors.log", "*.tmp.*"]))

    def test_the_writer_creates_it_with_the_rest_of_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# D\nWhy.\n")
            write_memory(tmp, "file-change")
            self.assertTrue(os.path.isfile(os.path.join(tmp, ".continuity", ".gitignore")))


@unittest.skipUnless(shutil.which("git"), "git is not installed")
class TestWithRealGit(unittest.TestCase):
    def git(self, root, *args):
        return subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True)

    def test_local_files_are_ignored_and_project_memory_is_not(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.git(tmp, "init", "-q")
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            ensure_gitignore(store)
            for rel in LOCAL_ONLY + PROJECT_MEMORY:
                path = os.path.join(store, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                if not os.path.exists(path):
                    open(path, "w").close()
            for rel in LOCAL_ONLY:
                ignored = self.git(tmp, "check-ignore", "-q", ".continuity/" + rel).returncode == 0
                self.assertTrue(ignored, rel + " should be ignored")
            for rel in PROJECT_MEMORY:
                ignored = self.git(tmp, "check-ignore", "-q", ".continuity/" + rel).returncode == 0
                self.assertFalse(ignored, rel + " is project memory and must not be ignored")

    def test_git_add_all_stages_exactly_the_project_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.git(tmp, "init", "-q")
            stage(tmp, "decision", "# D\nWhy.\n")
            write_memory(tmp, "file-change")
            stage(tmp, "task", "# T\nOne.\n", "20260912T140502Z-2")  # left staged on purpose
            open(os.path.join(tmp, ".continuity", ".turn-edited"), "w").close()
            open(os.path.join(tmp, ".continuity", "errors.log"), "w").close()
            self.git(tmp, "add", "-A")
            staged = set(self.git(tmp, "diff", "--cached", "--name-only").stdout.split())
            self.assertIn(".continuity/decisions.md", staged)
            self.assertIn(".continuity/state.md", staged)
            self.assertIn(".continuity/.gitignore", staged)
            self.assertTrue(any(p.startswith(".continuity/sessions/") for p in staged))
            self.assertFalse([p for p in staged if ".staged" in p or p.endswith((".turn-edited", "errors.log"))], staged)


if __name__ == "__main__":
    unittest.main()
