"""tests/test_seed_lock_naming_us3.py — CONTINUI-18 US3 coverage.

Rounds out the "keep working when memory breaks" story with the cases not
already covered by test_seed_store.py, test_write_memory_basic.py,
test_write_memory_unwritable_store.py, and test_select_context_corruption_us3.py:

  - Seeding logs a failure per individual seed file that fails to write,
    without that one failure stopping the other three seeds (lib/write_memory.py
    -> _seed_store).
  - The `updated_at` a seed stamps into state.md is in the exact format
    lib/select_context.py's `_read_state` requires to accept the file at all.
  - Every failure kind this story exercises — a seed write, a durable-file
    write, and a durable-file read — is logged under the `seed-X`/`write-X`/
    `read-X` operation naming data-model.md's Failure Log Entry rule pins,
    not some other ad hoc label.
  - `metadata_check_and_migrate` runs, and can veto the write, before
    `_seed_store` ever touches the store (write_memory()'s ordering).
  - A lock that is already held is logged and the write it would have made
    never lands, not even partially.
  - select_context() still surfaces every valid entry across all three
    durable files when each one also carries an isolated corrupt entry.
"""

import os
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

import lib.migrate as migrate_module
import lib.write_memory as write_memory_module
from lib.lock import lock_acquire as real_lock_acquire, lock_path
from lib.select_context import _entries, _read_state, select_context
from lib.write_memory import SEED_FILES, _append_entries, write_memory

OPERATION_RE = re.compile(r"^(read|write|seed)-[a-z]+$")


def stage(project_root, kind, body, suffix="20260912T140501Z-4242"):
    path = os.path.join(
        project_root, ".continuity", ".staged", "{}-{}.md".format(kind, suffix)
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def read_errors_log(store):
    path = os.path.join(store, "errors.log")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def log_fields(line):
    return [part.strip() for part in line.rstrip("\n").split("|")]


class TestSeedingLogsPerFileFailure(unittest.TestCase):
    def test_one_unseedable_file_is_logged_without_blocking_the_others(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            stage(tmp, "task", "Do the thing\n")

            # seed_store only attempts to write a target that does not yet
            # exist, so the way to make one file's seed fail in isolation is
            # to fail its write call directly rather than pre-occupy the
            # path -- a pre-existing file/dir would just be skipped as
            # "already there" before any write is attempted. The seam is in
            # lib/migrate.py, where seed_store lives.
            real_atomic_write = migrate_module.atomic_write

            def fail_decisions_only(target, content):
                if os.path.basename(target) == "decisions.md":
                    raise OSError("simulated failure seeding decisions.md")
                return real_atomic_write(target, content)

            with patch.object(migrate_module, "atomic_write", fail_decisions_only):
                write_memory(tmp, "file-change")

            self.assertFalse(os.path.exists(os.path.join(store, "decisions.md")))
            for name in ("state.md", "tasks.md", "learnings.md"):
                self.assertTrue(
                    os.path.isfile(os.path.join(store, name)),
                    "{} should still be seeded despite decisions.md failing".format(name),
                )

            log = read_errors_log(store)
            self.assertIn("seed-decisions", log)
            decisions_lines = [line for line in log.splitlines() if "seed-decisions" in line]
            self.assertEqual(len(decisions_lines), 1)
            fields = log_fields(decisions_lines[0])
            self.assertEqual(fields[1], "seed-decisions")
            self.assertEqual(fields[2], "write-failed")
            # And no failure is logged for the three seeds that succeeded.
            logged_operations = {
                log_fields(line)[1] for line in log.splitlines() if line.strip()
            }
            for name in ("state", "tasks", "learnings"):
                self.assertNotIn("seed-" + name, logged_operations)


class TestSeedTimestampMatchesStateReaderFormat(unittest.TestCase):
    def test_seeded_updated_at_is_the_exact_format_the_reader_requires(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Something\n\nBody.\n")
            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            state_text = read(os.path.join(store, "state.md"))
            match = re.search(r"updated_at:\s*(\S+)", state_text)
            self.assertIsNotNone(match, "seeded state.md must carry an updated_at field")

            # Exactly the ISO-8601 UTC shape lib/select_context.py's _read_state
            # (and lib/write_memory.py's own _now()) both produce: no
            # microseconds, no offset other than a bare Z.
            self.assertRegex(
                match.group(1), r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
            )

            result = _read_state(store)
            self.assertIsNotNone(
                result, "the reader must accept the seeded timestamp, not drop the file"
            )
            self.assertEqual(result[0], match.group(1))


class TestFailureOperationNamingIsConsistent(unittest.TestCase):
    def test_seed_write_and_read_failures_all_use_the_x_dash_kind_naming(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")

            # seed-X: force the decisions.md seed write to fail. A pre-existing
            # path would just be skipped as "already there" (seed_store only
            # writes a target that is absent), so the write call itself has
            # to fail instead.
            stage(tmp, "task", "Do the thing\n")
            real_atomic_write = migrate_module.atomic_write

            def fail_decisions_only(target, content):
                if os.path.basename(target) == "decisions.md":
                    raise OSError("simulated failure seeding decisions.md")
                return real_atomic_write(target, content)

            with patch.object(migrate_module, "atomic_write", fail_decisions_only):
                write_memory(tmp, "file-change")

            # write-X: learnings.md is a directory, so _append_entries's own
            # atomic_write can create its temp file but can never replace it
            # onto the target — called directly so the failure is
            # deterministic rather than racing the lock/seed machinery above.
            # The write above already seeded it as an empty file, so it has
            # to be cleared before it can be replaced with a directory.
            os.remove(os.path.join(store, "learnings.md"))
            os.makedirs(os.path.join(store, "learnings.md"))
            _append_entries(store, "learnings.md", ["entry"])

            # read-X: state.md is missing its updated_at.
            write(
                os.path.join(store, "state.md"),
                "# Project state\n\n```\ncategory: state\n```\n\nNo updated_at.\n",
            )
            select_context(store)

            log = read_errors_log(store)
            operations = {log_fields(line)[1] for line in log.splitlines() if line.strip()}

            self.assertIn("seed-decisions", operations)
            self.assertIn("write-learnings", operations)
            self.assertIn("read-state", operations)
            for operation in operations:
                self.assertRegex(
                    operation,
                    OPERATION_RE,
                    "{} does not follow the read-X/write-X/seed-X naming".format(operation),
                )


class TestMetadataSchemaCheckGuardsSeedingOrder(unittest.TestCase):
    def test_unsupported_schema_prevents_seeding_from_running_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            staged = stage(tmp, "decision", "# Not written\n\nBody.\n")
            write(
                os.path.join(store, "metadata.json"),
                '{"schema_version": "9.0", "plugin_version": "9.0.0"}',
            )

            result = write_memory(tmp, "file-change")

            self.assertIsNone(result)
            self.assertTrue(os.path.exists(staged), "a vetoed store must not consume notes")
            for name in SEED_FILES:
                self.assertFalse(
                    os.path.exists(os.path.join(store, name)),
                    "{} must not be seeded once the schema check vetoes the store".format(
                        name
                    ),
                )


class TestLockFailurePreventsPartialWrites(unittest.TestCase):
    def test_held_lock_is_logged_and_leaves_no_partial_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            staged = stage(tmp, "decision", "# Should not land\n\nBody.\n")
            os.makedirs(lock_path(store))

            def fast_lock_acquire(path):
                # Same call the production code makes, just with a short
                # timeout so the test doesn't wait out the real 5s default.
                return real_lock_acquire(path, timeout=0.1)

            with patch.object(write_memory_module, "lock_acquire", fast_lock_acquire):
                result = write_memory_module.write_memory(tmp, "file-change")

            self.assertIsNone(result)
            self.assertTrue(os.path.exists(staged), "a lock failure must not consume notes")
            # _seed_store runs before the lock is even requested, so
            # decisions.md may exist as an empty seed — what must never
            # happen is the staged note landing inside it.
            decisions_path = os.path.join(store, "decisions.md")
            if os.path.exists(decisions_path):
                self.assertNotIn("Should not land", read(decisions_path))
            sessions_dir = os.path.join(store, "sessions")
            self.assertFalse(
                os.path.isdir(sessions_dir) and os.listdir(sessions_dir),
                "no handoff may be written while the lock is unavailable",
            )

            log = read_errors_log(store)
            lock_lines = [line for line in log.splitlines() if "lock-unavailable" in line]
            self.assertEqual(len(lock_lines), 1)
            fields = log_fields(lock_lines[0])
            self.assertEqual(fields[1], "write-memory")
            self.assertEqual(fields[2], "lock-unavailable")


class TestMultipleValidEntriesSurviveIsolatedCorruptionPerFile(unittest.TestCase):
    def test_valid_decisions_tasks_and_learnings_all_load_despite_one_bad_entry_each(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "decisions.md"),
                "## Decision: first valid decision\n\n"
                "```\ncaptured_at: 2026-09-10T10:00:00Z\ncategory: decision\n```\n\n"
                "Kept one.\n\n"
                "## Decision: corrupt, missing captured_at\n\n"
                "```\ncategory: decision\n```\n\nDropped.\n\n"
                "## Decision: second valid decision\n\n"
                "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: decision\n```\n\n"
                "Kept two.\n",
            )
            write(
                os.path.join(store, "tasks.md"),
                "## Task: first valid task\n\n"
                "```\ncaptured_at: 2026-09-10T10:00:00Z\ncategory: task\nstatus: active\n```\n\n"
                "Kept one.\n\n"
                "## Task: corrupt, bad status\n\n"
                "```\ncaptured_at: 2026-09-10T10:00:00Z\ncategory: task\nstatus: bogus\n```\n\n"
                "Dropped.\n\n"
                "## Task: second valid task\n\n"
                "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: task\nstatus: blocked\n```\n\n"
                "Kept two.\n",
            )
            write(
                os.path.join(store, "learnings.md"),
                "## Learning: first valid learning\n\n"
                "```\ncaptured_at: 2026-09-10T10:00:00Z\ncategory: learning\n```\n\n"
                "Kept one.\n\n"
                "## Learning: corrupt, missing category\n\n"
                "```\ncaptured_at: 2026-09-10T10:00:00Z\n```\n\nDropped.\n\n"
                "## Learning: second valid learning\n\n"
                "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: learning\n```\n\n"
                "Kept two.\n",
            )

            context = select_context(store)

            for heading in (
                "first valid decision",
                "second valid decision",
                "first valid task",
                "second valid task",
                "first valid learning",
                "second valid learning",
            ):
                self.assertIn(heading, context)
            for heading in (
                "corrupt, missing captured_at",
                "corrupt, bad status",
                "corrupt, missing category",
            ):
                self.assertNotIn(heading, context)

            # Read the log from this one select_context() call before any
            # further reparse below adds its own lines — each _entries() call
            # logs afresh (there is no cache), so re-reading the log after a
            # second parse would double-count what a single session's read
            # actually produced.
            log = read_errors_log(store)
            for operation in ("read-decisions", "read-tasks", "read-learnings"):
                matching = [line for line in log.splitlines() if operation in line]
                self.assertEqual(
                    len(matching),
                    1,
                    "{} should log exactly one corrupted-count line".format(operation),
                )
                self.assertIn("1 of 3 entries skipped as invalid", matching[0])

            decisions = _entries(store, "decisions.md")
            tasks = _entries(store, "tasks.md", require_status=True)
            learnings = _entries(store, "learnings.md")
            self.assertEqual(len(decisions), 2)
            self.assertEqual(len(tasks), 2)
            self.assertEqual(len(learnings), 2)


if __name__ == "__main__":
    unittest.main()
