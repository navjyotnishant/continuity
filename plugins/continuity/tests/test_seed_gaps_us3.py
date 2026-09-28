"""tests/test_seed_gaps_us3.py — CONTINUI-18 US3 coverage, gaps left by the
QA analyst's case list once cross-checked against the implementation.

Four cases the other US3 test files did not isolate:

  - The raw seed *templates* for decisions.md/tasks.md — as opposed to a
    seed that immediately gets a real entry written into it by the same
    write — must themselves parse to "no entries yet" with nothing logged.
    Every existing seeding test stages a `decision`/`task` note, so the
    seeded file under test always already has a real entry by the time it's
    read back; the untouched template shape was never independently
    checked.
  - _seed_store logs a per-file write failure for *each* file that fails,
    not just the one the existing test exercises in isolation.
  - A corrupted entry with a missing `captured_at` is only exercised
    directly against decisions.md elsewhere; tasks.md and learnings.md share
    the same `_is_valid` check but that sharing was never itself verified.
  - A store missing exactly one of the four seed files (as opposed to all
    four) is a distinct partial-store shape from the "only metadata.json"
    case tests/test_seed_store.py already covers.
"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

import lib.migrate as migrate_module
import lib.write_memory as write_memory_module
from lib.select_context import _entries, select_context
from lib.write_memory import SEED_FILES, write_memory


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


class TestFreshSeedTemplatesParseCleanly(unittest.TestCase):
    def test_untouched_decisions_and_tasks_seeds_parse_to_no_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Stage only a learning, so decisions.md and tasks.md get seeded
            # but never receive a real entry — proving the bare template
            # shape (not one already carrying content) reads back clean.
            stage(tmp, "learning", "# A learning\n\nBody.\n")

            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            self.assertEqual(_entries(store, "decisions.md"), [])
            self.assertEqual(_entries(store, "tasks.md", require_status=True), [])
            self.assertEqual(
                read_errors_log(store), "", "a fresh seed must never be logged as corrupted"
            )

    def test_untouched_seeds_contribute_no_section_to_injected_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "learning", "# A learning\n\nBody.\n")
            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            context = select_context(store)

            self.assertIn("## Recent learnings", context)
            self.assertNotIn("## Recent decisions", context)
            self.assertNotIn("## Active tasks", context)


class TestAllFourSeedFilesCanFailIndependently(unittest.TestCase):
    def test_every_seed_write_failure_is_logged_on_its_own_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            stage(tmp, "task", "Do the thing\n")

            def fail_every_seed(target, _content):
                raise OSError("simulated failure for " + os.path.basename(target))

            # Seeding lives in lib/migrate.py (seed_store) and the durable
            # append in lib/write_memory.py, so both writers have to fail for
            # a file to stay absent once its seed failed.
            with patch.object(migrate_module, "atomic_write", fail_every_seed):
                with patch.object(write_memory_module, "atomic_write", fail_every_seed):
                    write_memory(tmp, "file-change")

            for name in SEED_FILES:
                self.assertFalse(
                    os.path.exists(os.path.join(store, name)),
                    "{} must not exist once its seed write failed".format(name),
                )

            log = read_errors_log(store)
            lines = log.splitlines()
            for name in SEED_FILES:
                stem = name[: -len(".md")]
                matching = [line for line in lines if "seed-" + stem in line]
                self.assertEqual(
                    len(matching),
                    1,
                    "seed-{} must be logged exactly once, not {} times".format(
                        stem, len(matching)
                    ),
                )
                fields = log_fields(matching[0])
                self.assertEqual(fields[1], "seed-" + stem)
                self.assertEqual(fields[2], "write-failed")


class TestIsolatedCapturedAtCorruptionAcrossFileKinds(unittest.TestCase):
    def test_task_missing_captured_at_is_skipped_and_logged_like_a_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "tasks.md"),
                "## Task: missing its captured_at\n\n"
                "```\ncategory: task\nstatus: active\n```\n\n"
                "Should be skipped.\n",
            )

            context = select_context(store)

            self.assertNotIn("missing its captured_at", context)
            self.assertNotIn("## Active tasks", context)
            log = read_errors_log(store)
            fields = log_fields(log.splitlines()[0])
            self.assertEqual(fields[1], "read-tasks")
            self.assertEqual(fields[2], "corrupted")
            self.assertIn("1 of 1 entries skipped as invalid", fields[3])

    def test_learning_missing_captured_at_is_skipped_and_logged_like_a_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "learnings.md"),
                "## Learning: missing its captured_at\n\n"
                "```\ncategory: learning\n```\n\n"
                "Should be skipped.\n",
            )

            context = select_context(store)

            self.assertNotIn("missing its captured_at", context)
            self.assertNotIn("## Recent learnings", context)
            log = read_errors_log(store)
            fields = log_fields(log.splitlines()[0])
            self.assertEqual(fields[1], "read-learnings")
            self.assertEqual(fields[2], "corrupted")
            self.assertIn("1 of 1 entries skipped as invalid", fields[3])


class TestPartialStoreMissingExactlyOneSeedFile(unittest.TestCase):
    def test_session_starts_successfully_missing_only_learnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "state.md"),
                "```\nupdated_at: 2026-09-11T09:00:00Z\n```\n",
            )
            write(os.path.join(store, "decisions.md"), "# Decisions\n")
            write(os.path.join(store, "tasks.md"), "# Tasks\n")
            # learnings.md deliberately absent.

            context = select_context(store)

            self.assertIsInstance(context, str)
            self.assertFalse(
                os.path.exists(os.path.join(store, "errors.log")),
                "one absent seed file among otherwise-present siblings is not a failure",
            )

    def test_write_against_a_store_missing_only_learnings_fills_in_just_that_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "state.md"),
                "```\nupdated_at: 2026-09-11T09:00:00Z\n```\n",
            )
            custom_decisions = "# Decisions\n\n## Decision: Hand-written\n\nKeep me.\n"
            write(os.path.join(store, "decisions.md"), custom_decisions)
            write(os.path.join(store, "tasks.md"), "# Tasks\n")
            stage(tmp, "learning", "# New learning\n\nBody.\n")

            write_memory(tmp, "file-change")

            self.assertEqual(read(os.path.join(store, "decisions.md")), custom_decisions)
            self.assertTrue(os.path.isfile(os.path.join(store, "learnings.md")))
            self.assertIn(
                "New learning", read(os.path.join(store, "learnings.md"))
            )


if __name__ == "__main__":
    unittest.main()
