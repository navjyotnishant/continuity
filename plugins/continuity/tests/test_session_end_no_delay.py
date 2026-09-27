"""tests/test_session_end_no_delay.py — CONTINUI-12 (US2: Never notice
Continuity is running).

`tests/test_detach.py` already proves `hooks/session-end.py` returns fast
against a *synthetic* writer stub that sleeps. This proves the same
property against the *real* `lib/write_memory.py`, doing real consolidation
work (secret scan, durable-file append, handoff write) over actual staged
notes — so a future change that makes the hook itself do work before
launching the writer (rather than launching-and-returning) would be caught
here even if the synthetic-stub test above stayed green.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

SESSION_END_HOOK = os.path.join(REPO_ROOT, "hooks", "session-end.py")

# Generous enough to absorb interpreter startup for the hook process itself;
# far too tight for a real write_memory.py pass (which itself does file I/O
# and a secret scan) to have completed within it.
RETURN_WITHIN_SECONDS = 0.5


def stage_note(continuity_dir_path, suffix):
    staged = os.path.join(continuity_dir_path, ".staged")
    os.makedirs(staged, exist_ok=True)
    path = os.path.join(staged, "decision-{}.md".format(suffix))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("# Real decision\n\nBody text for a real staged note.\n")
    return path


def run_hook(payload, timeout=30):
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, SESSION_END_HOOK],
        input=json.dumps(payload),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    return result, time.monotonic() - started


class TestSessionEndReturnsBeforeTheRealWriterCouldPossiblyFinish(unittest.TestCase):
    def test_hook_returns_promptly_even_with_real_staged_work_pending(self):
        with tempfile.TemporaryDirectory() as project:
            continuity_dir_path = os.path.join(project, ".continuity")
            stage_note(continuity_dir_path, "20260912T140501Z-1")

            result, elapsed = run_hook({"session_id": "s", "cwd": project})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertLess(elapsed, RETURN_WITHIN_SECONDS)

    def test_hook_returns_promptly_with_no_staged_work_at_all(self):
        with tempfile.TemporaryDirectory() as project:
            result, elapsed = run_hook({"session_id": "s", "cwd": project})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(elapsed, RETURN_WITHIN_SECONDS)

    def test_the_real_writer_eventually_consolidates_after_the_hook_already_returned(self):
        with tempfile.TemporaryDirectory() as project:
            continuity_dir_path = os.path.join(project, ".continuity")
            stage_note(continuity_dir_path, "20260912T140502Z-2")

            result, elapsed = run_hook({"session_id": "s", "cwd": project})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(elapsed, RETURN_WITHIN_SECONDS)

            decisions_path = os.path.join(continuity_dir_path, "decisions.md")
            deadline = time.monotonic() + 10.0
            while time.monotonic() < deadline and not os.path.exists(decisions_path):
                time.sleep(0.05)

            self.assertTrue(
                os.path.exists(decisions_path),
                "the detached writer never actually ran to completion",
            )


if __name__ == "__main__":
    unittest.main()
