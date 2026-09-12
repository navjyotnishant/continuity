"""tests/test_checkpoint_cli.py — /continuity-checkpoint's synchronous CLI contract.

commands/continuity-checkpoint.md Step 2/3: the command runs
`python3 lib/write_memory.py "$CLAUDE_PROJECT_DIR" explicit-checkpoint`
synchronously (there is no detach — the user asked for this and is
waiting) and relays the writer's own one-line result unchanged. Step 2 is
never skipped by a Step 1 that staged nothing: the writer always runs and
reports "Nothing new to checkpoint" rather than the command short-circuiting.
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from tests.test_write_memory_basic import sessions_files, stage

WRITER = os.path.join(REPO_ROOT, "lib", "write_memory.py")


def run_checkpoint(tmp):
    return subprocess.run(
        [sys.executable, WRITER, tmp, "explicit-checkpoint"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )


class TestCheckpointOutputFormat(unittest.TestCase):
    def test_staged_content_reports_checkpoint_written_to_the_sessions_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Checkpoint now\n\nBody.\n")

            result = run_checkpoint(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            match = re.match(r"^Checkpoint written to (.+)\n?$", result.stdout)
            self.assertIsNotNone(match, result.stdout)
            reported_path = match.group(1).strip()

            expected_suffix = os.path.join(".continuity", "sessions")
            self.assertIn(expected_suffix, reported_path)
            self.assertTrue(reported_path.endswith(".md"))
            self.assertTrue(
                os.path.isfile(reported_path), "reported path must be the real handoff file"
            )


class TestCheckpointRunsSynchronously(unittest.TestCase):
    def test_handoff_file_exists_the_instant_the_process_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "Wire the explicit checkpoint path\n")

            result = run_checkpoint(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            # No polling loop, unlike capture-trigger's detached-writer tests
            # (tests/test_write_memory_basic.py's wait_for_handoff): a
            # blocking call must leave the result already on disk the
            # moment subprocess.run returns.
            self.assertEqual(len(sessions_files(tmp)), 1)


class TestCheckpointAlwaysRunsTheWriter(unittest.TestCase):
    def test_nothing_staged_still_runs_the_writer_to_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".continuity", ".staged"))

            result = run_checkpoint(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Nothing new to checkpoint", result.stdout)
            self.assertEqual(sessions_files(tmp), [])

    def test_no_continuity_directory_at_all_still_runs_the_writer_to_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_checkpoint(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Nothing new to checkpoint", result.stdout)


if __name__ == "__main__":
    unittest.main()
