"""tests/test_fail_open.py — US3: keep working when memory breaks (T025).

Drives the four documented failure modes end to end, through the same entry
points Claude Code uses (`hooks/session-start.py` on stdin,
`lib/write_memory.py` as a subprocess), and asserts the same three things of
each: the entry point still succeeds, every *other* valid file still loads,
and the failure is visible only in `.continuity/errors.log`.

  (a) `.continuity/` missing entirely      — "no history yet", or seeded
  (b) `decisions.md` corrupted             — logged `corrupted`, siblings load
  (c) `state.md` unreadable (chmod 000)    — logged `unreadable`, siblings load
  (d) `.continuity/` unwritable during a write — clean abort, no partial file

Case (d) deliberately does not assert on `errors.log`: with the store itself
unwritable the log append fails too, and data-model.md's Failure Log Entry
rule names that as the one failure Continuity does not try to log.
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

SESSION_START_HOOK = os.path.join(REPO_ROOT, "hooks", "session-start.py")
WRITE_MEMORY = os.path.join(REPO_ROOT, "lib", "write_memory.py")

VALID_DECISION = (
    "## Decision: valid sibling\n\n"
    "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: decision\n```\n\n"
    "Must still load when another file is broken.\n"
)

# chmod is advisory for root, and native Windows ignores the POSIX mode bits
# outright, so the permission cases prove nothing there.
PERMISSIONS_ENFORCED = os.name != "nt" and getattr(os, "geteuid", lambda: 1)() != 0


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def run_session_start(project_root):
    """Drive hooks/session-start.py exactly as Claude Code does."""
    return subprocess.run(
        [sys.executable, SESSION_START_HOOK],
        input=json.dumps({"session_id": "s", "cwd": project_root}),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )


def run_write_memory(project_root, trigger_kind="explicit-checkpoint"):
    return subprocess.run(
        [sys.executable, WRITE_MEMORY, project_root, trigger_kind],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )


def injected_context(result):
    """The additionalContext the hook emitted, or "" when it injected none."""
    payload = json.loads(result.stdout)
    return payload["hookSpecificOutput"].get("additionalContext", "")


def error_lines(store):
    try:
        return [line for line in read(os.path.join(store, "errors.log")).splitlines() if line]
    except OSError:
        return []


def temp_debris(store):
    """Any `<target>.tmp.*` file an interrupted atomic write left behind."""
    found = []
    for root, _dirs, files in os.walk(store):
        found.extend(name for name in files if ".tmp." in name)
    return found


class RestoreMode:
    """chmod a path for the duration of a block, then put the mode back.

    TemporaryDirectory cleanup cannot remove a tree it has no permission to
    walk, so a test that drops a mode must restore it even when it fails.
    """

    def __init__(self, path, mode):
        self.path = path
        self.mode = mode

    def __enter__(self):
        self.original = stat.S_IMODE(os.stat(self.path).st_mode)
        os.chmod(self.path, self.mode)
        return self

    def __exit__(self, *_exc):
        os.chmod(self.path, self.original)
        return False


class TestMissingStore(unittest.TestCase):
    """(a) `.continuity/` does not exist — "no history yet", not an error."""

    def test_session_start_injects_nothing_and_creates_nothing(self):
        with tempfile.TemporaryDirectory() as project:
            result = run_session_start(project)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(injected_context(result), "")
            self.assertFalse(os.path.exists(os.path.join(project, ".continuity")))

    def test_writer_with_a_staged_note_seeds_the_whole_store(self):
        """T029: a first-ever write lands in a populated, valid store."""
        with tempfile.TemporaryDirectory() as project:
            store = os.path.join(project, ".continuity")
            write(
                os.path.join(store, ".staged", "decision-20260912T140501Z-4242.md"),
                "# First ever decision\n\nNothing existed in the store before this.\n",
            )

            result = run_write_memory(project)

            self.assertEqual(result.returncode, 0, result.stderr)
            for name in ("state.md", "decisions.md", "tasks.md", "learnings.md"):
                self.assertTrue(
                    os.path.isfile(os.path.join(store, name)),
                    name + " must be seeded by the first write",
                )
            metadata = json.loads(read(os.path.join(store, "metadata.json")))
            self.assertEqual(metadata["schema_version"], "1.0")
            self.assertIn("First ever decision", read(os.path.join(store, "decisions.md")))
            self.assertEqual(error_lines(store), [], "seeding a store is not a failure")

    def test_a_seeded_store_reads_back_cleanly_on_the_next_session(self):
        """The seed must be valid input to its own reader, not new corruption."""
        with tempfile.TemporaryDirectory() as project:
            store = os.path.join(project, ".continuity")
            write(
                os.path.join(store, ".staged", "decision-20260912T140501Z-4242.md"),
                "# Seeded then read back\n\nBody.\n",
            )
            run_write_memory(project)

            result = run_session_start(project)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Seeded then read back", injected_context(result))
            self.assertEqual(
                error_lines(store), [], "reading a freshly seeded store logs nothing"
            )


class TestCorruptedFile(unittest.TestCase):
    """(b) an entry missing `captured_at` invalidates that entry only."""

    def test_corrupted_entry_is_skipped_logged_and_siblings_still_load(self):
        with tempfile.TemporaryDirectory() as project:
            store = os.path.join(project, ".continuity")
            write(
                os.path.join(store, "decisions.md"),
                "## Decision: no captured_at anywhere\n\n"
                "```\ncategory: decision\n```\n\n"
                "Must be skipped.\n\n" + VALID_DECISION,
            )
            write(
                os.path.join(store, "learnings.md"),
                "## Learning: an untouched other file\n\n"
                "```\ncaptured_at: 2026-09-11T11:00:00Z\ncategory: learning\n```\n\n"
                "Must still load.\n",
            )

            result = run_session_start(project)

            self.assertEqual(result.returncode, 0, result.stderr)
            context = injected_context(result)
            self.assertNotIn("no captured_at anywhere", context)
            self.assertIn("valid sibling", context)
            self.assertIn("an untouched other file", context)

            logged = [line for line in error_lines(store) if "| corrupted |" in line]
            self.assertTrue(logged, "a skipped entry must be logged: " + str(error_lines(store)))
            self.assertTrue(any("decisions" in line for line in logged))
            self.assertFalse(
                any("Must be skipped" in line for line in error_lines(store)),
                "errors.log must never carry raw file content",
            )

    def test_state_without_updated_at_is_dropped_whole_and_logged(self):
        with tempfile.TemporaryDirectory() as project:
            store = os.path.join(project, ".continuity")
            write(
                os.path.join(store, "state.md"),
                "# Project state\n\n```\nsummary: no updated_at field\n```\n\n"
                "Halfway through a refactor.\n",
            )
            write(os.path.join(store, "decisions.md"), VALID_DECISION)

            result = run_session_start(project)

            self.assertEqual(result.returncode, 0, result.stderr)
            context = injected_context(result)
            self.assertNotIn("Halfway through a refactor", context)
            self.assertIn("valid sibling", context)
            self.assertTrue(
                any(
                    "| corrupted |" in line and "state" in line
                    for line in error_lines(store)
                ),
                "an unparseable state.md must be logged: " + str(error_lines(store)),
            )


@unittest.skipUnless(PERMISSIONS_ENFORCED, "chmod is not enforced for this user/platform")
class TestUnreadableFile(unittest.TestCase):
    """(c) an unreadable file is treated as absent for that file only."""

    def test_unreadable_state_is_logged_and_other_files_still_load(self):
        with tempfile.TemporaryDirectory() as project:
            store = os.path.join(project, ".continuity")
            state = os.path.join(store, "state.md")
            write(
                state,
                "# Project state\n\n```\nupdated_at: 2026-09-11T09:00:00Z\n```\n\n"
                "Unreadable, so never injected.\n",
            )
            write(os.path.join(store, "decisions.md"), VALID_DECISION)

            with RestoreMode(state, 0o000):
                result = run_session_start(project)

                self.assertEqual(result.returncode, 0, result.stderr)
                context = injected_context(result)
                self.assertNotIn("Unreadable, so never injected", context)
                self.assertIn("valid sibling", context)
                self.assertTrue(
                    any(
                        "| unreadable |" in line and "state" in line
                        for line in error_lines(store)
                    ),
                    "an unreadable file must be logged: " + str(error_lines(store)),
                )


@unittest.skipUnless(PERMISSIONS_ENFORCED, "chmod is not enforced for this user/platform")
class TestUnwritableStore(unittest.TestCase):
    """(d) a write into an unwritable store aborts cleanly, losing nothing."""

    def stage_one_note(self, project):
        return write(
            os.path.join(
                project, ".continuity", ".staged", "decision-20260912T140501Z-4242.md"
            ),
            "# Staged while the store was writable\n\nBody.\n",
        )

    def test_read_only_store_aborts_the_write_and_keeps_the_staged_note(self):
        with tempfile.TemporaryDirectory() as project:
            store = os.path.join(project, ".continuity")
            staged = self.stage_one_note(project)

            # r-x: the staged note is still listable and readable, but no new
            # file (the lock, the durable file, the handoff) can be created.
            with RestoreMode(store, 0o500):
                result = run_write_memory(project)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                os.path.exists(staged), "an aborted write must not consume the note"
            )
            self.assertFalse(os.path.exists(os.path.join(store, "decisions.md")))
            self.assertEqual(temp_debris(store), [], "no partial file may be left behind")

    def test_unlistable_store_is_a_clean_no_op(self):
        with tempfile.TemporaryDirectory() as project:
            store = os.path.join(project, ".continuity")
            self.stage_one_note(project)

            with RestoreMode(store, 0o000):
                result = run_write_memory(project)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(temp_debris(store), [], "no partial file may be left behind")


if __name__ == "__main__":
    unittest.main()
