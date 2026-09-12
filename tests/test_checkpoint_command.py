"""tests/test_checkpoint_command.py — /continuity-checkpoint with nothing
staged (commands/continuity-checkpoint.md, Step 2/3).

The command's Step 2 is exactly `python3 lib/write_memory.py
"$CLAUDE_PROJECT_DIR" explicit-checkpoint`; its Step 3 says to relay the
writer's one-line result unchanged. With nothing staged, that result must be
"Nothing new to checkpoint" and no new file must appear anywhere under
`.continuity/` — a checkpoint with nothing new is a legitimate outcome, not
a failure (FR-011).
"""

import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

WRITE_MEMORY = os.path.join(REPO_ROOT, "lib", "write_memory.py")


def snapshot(continuity_dir_path):
    """All file paths under `.continuity/`, or None if it does not exist."""
    if not os.path.isdir(continuity_dir_path):
        return None
    found = []
    for root, _dirs, files in os.walk(continuity_dir_path):
        for name in files:
            found.append(os.path.relpath(os.path.join(root, name), continuity_dir_path))
    return sorted(found)


class TestCheckpointCommandWithNothingStaged(unittest.TestCase):
    def run_checkpoint(self, project_root):
        return subprocess.run(
            [sys.executable, WRITE_MEMORY, project_root, "explicit-checkpoint"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )

    def test_no_continuity_dir_at_all_outputs_nothing_new_and_creates_no_file(self):
        with tempfile.TemporaryDirectory() as project:
            result = self.run_checkpoint(project)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "Nothing new to checkpoint")
            self.assertIsNone(
                snapshot(os.path.join(project, ".continuity")),
                "an empty checkpoint must not create .continuity/ at all",
            )

    def test_empty_staged_dir_outputs_nothing_new_and_leaves_the_store_untouched(self):
        with tempfile.TemporaryDirectory() as project:
            store = os.path.join(project, ".continuity")
            os.makedirs(os.path.join(store, ".staged"))
            before = snapshot(store)

            result = self.run_checkpoint(project)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "Nothing new to checkpoint")
            self.assertEqual(snapshot(store), before, "no new file must appear")


if __name__ == "__main__":
    unittest.main()
