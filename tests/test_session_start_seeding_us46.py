"""tests/test_session_start_seeding_us46.py — CONTINUI-46 coverage.

hooks/session-start.py now calls lib/migrate.py's seed_store directly when it
finds no `.continuity/` (see build_context). test_seed_gaps_us3.py and
test_seed_lock_naming_us3.py already cover per-file seed failures through the
lib/write_memory.py -> write_memory() entry point; this file covers the same
guarantees through the *other* caller of seed_store — the SessionStart hook
itself — plus the synchronous-seeding and clean-success cases that are
specific to running on this path rather than the writer's:

  - One seed file failing to write does not stop the other three from being
    seeded (both callers share lib/migrate.py's seed_store, so the failure
    isolation is the same code, but nothing yet drove it through the hook).
  - Each failure is logged under its own seed-<name> operation, not lumped
    together.
  - Seeding runs synchronously inside the hook process — no subprocess or
    thread is spawned for it, unlike write_memory's fire-and-forget model
    (CLAUDE.md's FR-010 is about *writer* dispatch, not this hook) — so the
    seeded files are already on disk by the time main() returns.
  - A clean seed writes no errors.log at all.
"""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

import lib.migrate as migrate_module
from lib.migrate import SEED_FILES

SESSION_START_HOOK = os.path.join(REPO_ROOT, "hooks", "session-start.py")

_SPEC = importlib.util.spec_from_file_location("session_start", SESSION_START_HOOK)
session_start = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(session_start)


class mock_stdio:
    """Swap sys.stdin/stdout for the duration of one hook invocation."""

    def __init__(self, stdin, stdout):
        self.stdin = stdin
        self.stdout = stdout

    def __enter__(self):
        self._real_stdin, sys.stdin = sys.stdin, self.stdin
        self._real_stdout, sys.stdout = sys.stdout, self.stdout
        return self

    def __exit__(self, *_exc):
        sys.stdin = self._real_stdin
        sys.stdout = self._real_stdout
        return False


def run_hook_in_process(cwd):
    """Drive main() over a stdin payload and return the parsed output."""
    stdout = io.StringIO()
    with mock_stdio(io.StringIO(json.dumps({"session_id": "s", "cwd": cwd})), stdout):
        session_start.main()
    return json.loads(stdout.getvalue())


def read_errors_log(store):
    path = os.path.join(store, "errors.log")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def log_fields(line):
    return [part.strip() for part in line.rstrip("\n").split("|")]


class TestOneSeedFailureDoesNotBlockTheOthers(unittest.TestCase):
    def test_decisions_seed_failing_still_leaves_the_other_three_seeded(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            real_atomic_write = migrate_module.atomic_write

            def fail_decisions_only(target, content):
                if os.path.basename(target) == "decisions.md":
                    raise OSError("simulated failure seeding decisions.md")
                return real_atomic_write(target, content)

            with patch.object(migrate_module, "atomic_write", fail_decisions_only):
                run_hook_in_process(tmp)

            self.assertFalse(os.path.exists(os.path.join(store, "decisions.md")))
            for name in ("state.md", "tasks.md", "learnings.md"):
                self.assertTrue(
                    os.path.isfile(os.path.join(store, name)),
                    "{} should still be seeded despite decisions.md failing".format(name),
                )

    def test_every_seed_file_can_fail_independently_of_the_others(self):
        for target_name in SEED_FILES:
            with tempfile.TemporaryDirectory() as tmp:
                store = os.path.join(tmp, ".continuity")
                real_atomic_write = migrate_module.atomic_write

                def fail_only_target(target, content, _target_name=target_name):
                    if os.path.basename(target) == _target_name:
                        raise OSError("simulated failure for " + _target_name)
                    return real_atomic_write(target, content)

                with patch.object(migrate_module, "atomic_write", fail_only_target):
                    run_hook_in_process(tmp)

                self.assertFalse(os.path.exists(os.path.join(store, target_name)))
                for other in SEED_FILES:
                    if other == target_name:
                        continue
                    self.assertTrue(
                        os.path.isfile(os.path.join(store, other)),
                        "{} should still be seeded when only {} fails".format(
                            other, target_name
                        ),
                    )


class TestEachSeedFailureIsLoggedSeparately(unittest.TestCase):
    def test_failing_seed_files_each_get_their_own_seed_dash_name_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            real_atomic_write = migrate_module.atomic_write

            def fail_state_and_tasks(target, content):
                name = os.path.basename(target)
                if name in ("state.md", "tasks.md"):
                    raise OSError("simulated failure for " + name)
                return real_atomic_write(target, content)

            with patch.object(migrate_module, "atomic_write", fail_state_and_tasks):
                run_hook_in_process(tmp)

            log = read_errors_log(store)
            lines = [line for line in log.splitlines() if line.strip()]

            state_lines = [line for line in lines if "seed-state" in line]
            tasks_lines = [line for line in lines if "seed-tasks" in line]
            self.assertEqual(len(state_lines), 1)
            self.assertEqual(len(tasks_lines), 1)

            state_fields = log_fields(state_lines[0])
            tasks_fields = log_fields(tasks_lines[0])
            self.assertEqual(state_fields[1], "seed-state")
            self.assertEqual(state_fields[2], "write-failed")
            self.assertEqual(tasks_fields[1], "seed-tasks")
            self.assertEqual(tasks_fields[2], "write-failed")

            # decisions.md and learnings.md succeeded — no seed-* line for them.
            logged_operations = {log_fields(line)[1] for line in lines}
            self.assertNotIn("seed-decisions", logged_operations)
            self.assertNotIn("seed-learnings", logged_operations)


class TestSeedingIsSynchronous(unittest.TestCase):
    def test_no_subprocess_or_thread_is_spawned_to_seed(self):
        """Unlike write_memory's fire-and-forget writer, this hook seeds
        inline: nothing should reach for Popen/subprocess.run or a background
        thread just to create the store."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                subprocess, "Popen", side_effect=AssertionError("must not spawn a process")
            ), patch.object(
                subprocess, "run", side_effect=AssertionError("must not spawn a process")
            ), patch.object(
                threading, "Thread", side_effect=AssertionError("must not spawn a thread")
            ):
                run_hook_in_process(tmp)

            store = os.path.join(tmp, ".continuity")
            self.assertTrue(os.path.isdir(store))
            for name in SEED_FILES:
                self.assertTrue(os.path.isfile(os.path.join(store, name)))

    def test_seed_files_are_already_on_disk_the_instant_the_hook_returns(self):
        """No deferred/queued write: the four files exist synchronously,
        before any later session or process could have raced to create them."""
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")

            output = run_hook_in_process(tmp)

            self.assertNotIn("additionalContext", output.get("hookSpecificOutput", {}))
            for name in SEED_FILES:
                self.assertTrue(
                    os.path.isfile(os.path.join(store, name)),
                    "{} must exist synchronously once main() has returned".format(name),
                )


class TestCleanSeedWritesNoErrorsLog(unittest.TestCase):
    def test_errors_log_is_not_created_when_every_seed_write_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)

            store = os.path.join(tmp, ".continuity")
            self.assertFalse(os.path.exists(os.path.join(store, "errors.log")))

    def test_errors_log_is_not_created_by_a_real_subprocess_run_either(self):
        """Same guarantee driven the way Claude Code actually invokes the
        hook, not just the in-process call above."""
        with tempfile.TemporaryDirectory() as project:
            result = subprocess.run(
                [sys.executable, SESSION_START_HOOK],
                input=json.dumps({"session_id": "s", "cwd": project}),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            store = os.path.join(project, ".continuity")
            self.assertTrue(os.path.isdir(store))
            self.assertFalse(os.path.exists(os.path.join(store, "errors.log")))


if __name__ == "__main__":
    unittest.main()
