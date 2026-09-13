"""tests/test_seed_store.py — CONTINUI-18 US3: keep working when memory breaks.

Covers the missing-store and partial-store paths around CONTINUI-23's
seeding (lib/write_memory.py:_seed_store, templates/*.tmpl):

  - SessionStart with no `.continuity/` at all still starts clean and
    injects nothing (contracts/hook-io-contract.md -> SessionStart, FR-007).
  - The next write to that missing store seeds all four durable files
    (state.md, decisions.md, tasks.md, learnings.md), and those seeds parse
    back cleanly through the same reader SessionStart uses.
  - An existing seed file is never overwritten, whole-store or partial.
  - SessionStart tolerates a partial store (some seed files missing).
  - A write against a partial store completes only what is missing.
"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.select_context import _entries, _read_state
from lib.write_memory import SEED_FILES, write_memory

SESSION_START_HOOK = os.path.join(REPO_ROOT, "hooks", "session-start.py")

_SPEC = importlib.util.spec_from_file_location("session_start", SESSION_START_HOOK)
session_start = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(session_start)


class mock_stdio:
    """Swap sys.stdin/stdout for the duration of one hook invocation."""

    def __init__(self, stdin, stdout):
        self._stdin = stdin
        self._stdout = stdout

    def __enter__(self):
        self._orig_stdin, sys.stdin = sys.stdin, self._stdin
        self._orig_stdout, sys.stdout = sys.stdout, self._stdout

    def __exit__(self, *exc_info):
        sys.stdin = self._orig_stdin
        sys.stdout = self._orig_stdout


def run_session_start(cwd):
    payload = {"session_id": "s", "cwd": cwd}
    stdin = io.StringIO(json.dumps(payload))
    stdout = io.StringIO()
    with mock_stdio(stdin, stdout):
        rc = session_start.main()
    return rc, json.loads(stdout.getvalue())


def stage(project_root, kind, body, suffix="20260912T140501Z-4242"):
    path = os.path.join(
        project_root, ".continuity", ".staged", "{}-{}.md".format(kind, suffix)
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class TestSessionStartWithNoStore(unittest.TestCase):
    def test_session_starts_successfully_when_store_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, output = run_session_start(tmp)

            self.assertEqual(rc, 0)
            self.assertEqual(
                output["hookSpecificOutput"]["hookEventName"], "SessionStart"
            )

    def test_session_injects_no_context_when_store_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, output = run_session_start(tmp)

            self.assertNotIn(
                "additionalContext", output.get("hookSpecificOutput", {})
            )
            self.assertEqual(session_start.build_context(tmp), "")


class TestWriteSeedsAllFourFiles(unittest.TestCase):
    def test_write_against_missing_store_creates_all_four_seed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Something worth keeping\n\nBody.\n")

            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            for name in SEED_FILES:
                self.assertTrue(
                    os.path.isfile(os.path.join(store, name)),
                    "{} was not seeded".format(name),
                )

    def test_seed_files_parse_without_errors_on_next_session_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Something worth keeping\n\nBody.\n")
            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")

            # state.md must carry a parseable updated_at (its reader drops
            # the whole file otherwise).
            state = _read_state(store)
            self.assertIsNotNone(state)
            updated_at, _summary, _constraints = state
            self.assertTrue(updated_at)

            # The other three seeds are empty but well-formed: no entries,
            # and no error logged about them.
            self.assertEqual(_entries(store, "tasks.md", require_status=True), [])
            self.assertEqual(_entries(store, "learnings.md"), [])

            errors_path = os.path.join(store, "errors.log")
            if os.path.exists(errors_path):
                errors = read(errors_path)
                for name in SEED_FILES:
                    self.assertNotIn(name, errors)

            # And SessionStart over this store reads the seeded files back
            # cleanly: the one real decision comes through, and the three
            # still-empty seeds contribute no corruption noise.
            rc, output = run_session_start(tmp)
            self.assertEqual(rc, 0)
            context = output["hookSpecificOutput"]["additionalContext"]
            self.assertIn("Something worth keeping", context)
            self.assertNotIn("## Active tasks", context)
            self.assertNotIn("## Recent learnings", context)


class TestSeedFilesNeverOverwritten(unittest.TestCase):
    def test_existing_seed_files_are_left_alone_by_a_fresh_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            custom_state = "# hand-edited state\n\nupdated_at: 2020-01-01T00:00:00Z\n"
            with open(os.path.join(store, "state.md"), "w", encoding="utf-8") as handle:
                handle.write(custom_state)

            stage(tmp, "decision", "# New decision\n\nBody.\n")
            write_memory(tmp, "file-change")

            self.assertEqual(read(os.path.join(store, "state.md")), custom_state)

    def test_partially_built_store_only_fills_in_what_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            custom_decisions = "# Decisions\n\n## Decision: Hand-written\n\nKeep me.\n"
            with open(
                os.path.join(store, "decisions.md"), "w", encoding="utf-8"
            ) as handle:
                handle.write(custom_decisions)

            stage(tmp, "task", "Do the thing\n")
            write_memory(tmp, "file-change")

            # The pre-existing file is untouched...
            self.assertEqual(read(os.path.join(store, "decisions.md")), custom_decisions)
            # ...while the missing seeds got filled in.
            self.assertTrue(os.path.isfile(os.path.join(store, "state.md")))
            self.assertTrue(os.path.isfile(os.path.join(store, "learnings.md")))
            self.assertTrue(os.path.isfile(os.path.join(store, "tasks.md")))


class TestPartialStore(unittest.TestCase):
    def test_session_starts_successfully_with_missing_seed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            # A store missing every seed file except metadata is the most
            # partial store SessionStart can see (T029 has not run yet).
            with open(os.path.join(store, "metadata.json"), "w", encoding="utf-8") as handle:
                json.dump({"schema_version": "1.0", "plugin_version": "0.1.0"}, handle)

            rc, output = run_session_start(tmp)

            self.assertEqual(rc, 0)
            self.assertEqual(
                output["hookSpecificOutput"]["hookEventName"], "SessionStart"
            )
            self.assertNotIn(
                "additionalContext", output.get("hookSpecificOutput", {})
            )
            self.assertFalse(
                os.path.exists(os.path.join(store, "errors.log")),
                "an absent seed file is normal, not a failure to log",
            )


if __name__ == "__main__":
    unittest.main()
