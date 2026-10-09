"""tests/test_task_state_writer.py — the two writer paths data-model.md promises
but the writer did not implement: a task's status mutated in place, and
state.md rewritten in place from a `state` note.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.select_context import _entries, _read_state, select_context
import lib.write_memory as wm
from lib.write_memory import write_memory
from tests.test_write_memory_basic import read as read_path, stage


def read(tmp, name):
    return read_path(os.path.join(tmp, ".continuity", name))


def tasks(tmp):
    return _entries(os.path.join(tmp, ".continuity"), "tasks.md", require_status=True)


def status_of(entry):
    return entry["fields"]["status"]


class TestTaskStatus(unittest.TestCase):
    def test_note_without_status_is_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "# Write parser\nStub only.\n")
            write_memory(tmp, "file-change")
            (entry,) = tasks(tmp)
            self.assertEqual(status_of(entry), "active")

    def test_status_line_sets_status_and_leaves_the_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "# Write parser\nstatus: blocked\nWaiting on the grammar spec.\n")
            write_memory(tmp, "file-change")
            (entry,) = tasks(tmp)
            self.assertEqual(status_of(entry), "blocked")
            body = "\n".join(entry["body"])
            self.assertIn("grammar spec", body)
            self.assertNotIn("status:", body)

    def test_unrecognized_status_is_ignored_and_kept_in_the_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "# Write parser\nstatus: wibble\nSomething.\n")
            write_memory(tmp, "file-change")
            (entry,) = tasks(tmp)
            self.assertEqual(status_of(entry), "active")
            self.assertIn("status: wibble", "\n".join(entry["body"]))


class TestTaskUpdatesInPlace(unittest.TestCase):
    def test_same_title_updates_the_entry_instead_of_appending(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "# Write parser\nstatus: blocked\nWaiting on the grammar spec.\n")
            write_memory(tmp, "file-change")
            (first,) = tasks(tmp)
            captured = first["fields"]["captured_at"]

            stage(tmp, "task", "# Write parser\nstatus: done\nSplits on commas.\n")
            write_memory(tmp, "file-change")

            (entry,) = tasks(tmp)
            self.assertEqual(status_of(entry), "done")
            self.assertEqual(entry["fields"]["captured_at"], captured)
            self.assertTrue(entry["fields"].get("updated_at"))
            body = "\n".join(entry["body"])
            self.assertIn("Splits on commas", body)
            self.assertNotIn("grammar spec", body)

    def test_title_match_ignores_case_and_a_task_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "# Write Parser\nOne.\n")
            write_memory(tmp, "file-change")
            stage(tmp, "task", "# Task: write parser\nstatus: done\n")
            write_memory(tmp, "file-change")
            (entry,) = tasks(tmp)
            self.assertEqual(status_of(entry), "done")

    def test_update_without_status_keeps_the_existing_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "# Write parser\nstatus: done\nFinished.\n")
            write_memory(tmp, "file-change")
            stage(tmp, "task", "# Write parser\nAdded a docstring.\n")
            write_memory(tmp, "file-change")
            (entry,) = tasks(tmp)
            self.assertEqual(status_of(entry), "done")
            self.assertIn("docstring", "\n".join(entry["body"]))

    def test_title_line_instead_of_a_heading_still_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "# Implement parser\nstatus: blocked\nWaiting.\n")
            write_memory(tmp, "file-change")
            stage(tmp, "task", "title: Implement parser\nstatus: done\n\nDone.\n")
            write_memory(tmp, "file-change")
            (entry,) = tasks(tmp)
            self.assertEqual(status_of(entry), "done")
            self.assertEqual(entry["heading"], "Task: Implement parser")

    def test_a_different_title_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "# Write parser\nOne.\n")
            write_memory(tmp, "file-change")
            stage(tmp, "task", "# Write lexer\nTwo.\n")
            write_memory(tmp, "file-change")
            self.assertEqual(len(tasks(tmp)), 2)

    def test_two_notes_for_one_new_task_in_one_run_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "# Write parser\nstatus: active\nStarted.\n", "20260912T140501Z-1")
            stage(tmp, "task", "# Write parser\nstatus: done\nFinished.\n", "20260912T140502Z-2")
            write_memory(tmp, "file-change")
            (entry,) = tasks(tmp)
            self.assertEqual(status_of(entry), "done")

    def test_done_tasks_sort_after_open_ones_in_recall(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "# Old thing\nstatus: done\n")
            write_memory(tmp, "file-change")
            stage(tmp, "task", "# New thing\nstatus: blocked\n")
            write_memory(tmp, "file-change")
            context = select_context(os.path.join(tmp, ".continuity"))
            self.assertLess(context.index("New thing"), context.index("Old thing"))

    def test_other_entries_and_the_file_title_survive_an_update(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "# Keep me\nOne.\n", "20260912T140501Z-1")
            stage(tmp, "task", "# Change me\nTwo.\n", "20260912T140502Z-2")
            write_memory(tmp, "file-change")
            stage(tmp, "task", "# Change me\nstatus: done\n")
            write_memory(tmp, "file-change")
            text = read(tmp, "tasks.md")
            self.assertTrue(text.startswith("# Tasks"))
            self.assertIn("## Task: Keep me", text)
            self.assertEqual(text.count("## Task: Change me"), 1)


class TestRecallOrder(unittest.TestCase):
    def test_same_timestamp_entries_recall_newest_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            for i in range(1, 6):
                stage(tmp, "decision", "# Choice %d\nWhy %d.\n" % (i, i), "20260912T14%04dZ-%d" % (i, i))
            write_memory(tmp, "file-change")
            context = select_context(os.path.join(tmp, ".continuity"))
            self.assertLess(context.index("Choice 5"), context.index("Choice 1"))

    def test_recently_updated_open_task_outranks_a_newer_untouched_one(self):
        clock = {"now": "2026-09-12T14:00:01Z"}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(wm, "_now", lambda: clock["now"]):
            stage(tmp, "task", "# Old task\nOne.\n", "20260912T140001Z-1")
            write_memory(tmp, "file-change")
            clock["now"] = "2026-09-12T14:00:02Z"
            stage(tmp, "task", "# Newer task\nTwo.\n", "20260912T140002Z-2")
            write_memory(tmp, "file-change")
            clock["now"] = "2026-09-12T14:00:03Z"
            stage(tmp, "task", "# Old task\nstatus: blocked\nStuck now.\n", "20260912T140003Z-3")
            write_memory(tmp, "file-change")
            context = select_context(os.path.join(tmp, ".continuity"))
            self.assertLess(context.index("Old task"), context.index("Newer task"))


class TestStateNote(unittest.TestCase):
    def state(self, tmp):
        return _read_state(os.path.join(tmp, ".continuity"))

    def test_state_note_rewrites_state_md_and_reads_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(
                tmp,
                "state",
                "# Project state\nParser: comma split done.\nLexer: not started.\n\n"
                "## Constraints\n- Python 3.9 stdlib only\n",
            )
            write_memory(tmp, "file-change")
            updated_at, summary, constraints = self.state(tmp)
            self.assertTrue(updated_at)
            self.assertIn("Parser: comma split done.", summary)
            self.assertIn("- Python 3.9 stdlib only", constraints)

    def test_second_state_note_replaces_the_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "state", "Old summary.\n")
            write_memory(tmp, "file-change")
            stage(tmp, "state", "New summary.\n")
            write_memory(tmp, "file-change")
            text = read(tmp, "state.md")
            self.assertIn("New summary.", text)
            self.assertNotIn("Old summary.", text)
            self.assertEqual(text.count("updated_at:"), 1)

    def test_omitted_constraints_are_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "state", "Summary one.\n\nConstraints:\n- No network\n")
            write_memory(tmp, "file-change")
            stage(tmp, "state", "Summary two.\n")
            write_memory(tmp, "file-change")
            _, summary, constraints = self.state(tmp)
            self.assertEqual(summary, ["Summary two."])
            self.assertEqual(constraints, ["- No network"])

    def test_omitted_summary_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "state", "Keep this summary.\n")
            write_memory(tmp, "file-change")
            stage(tmp, "state", "## Constraints\n- New limit\n")
            write_memory(tmp, "file-change")
            _, summary, constraints = self.state(tmp)
            self.assertEqual(summary, ["Keep this summary."])
            self.assertEqual(constraints, ["- New limit"])

    def test_empty_state_note_does_not_wipe_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "state", "Real summary.\n")
            write_memory(tmp, "file-change")
            stage(tmp, "state", "# Project state\n\n")
            write_memory(tmp, "file-change")
            _, summary, _ = self.state(tmp)
            self.assertEqual(summary, ["Real summary."])

    def test_empty_state_note_leaves_the_file_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "state", "Real summary.\n")
            write_memory(tmp, "file-change")
            before = read(tmp, "state.md")
            stage(tmp, "state", "# Project state\n\n  \n")
            write_memory(tmp, "file-change")
            self.assertEqual(read(tmp, "state.md"), before)

    def test_newest_of_two_notes_in_one_run_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "state", "First.\n", "20260912T140501Z-1")
            stage(tmp, "state", "Second.\n", "20260912T140502Z-2")
            write_memory(tmp, "file-change")
            text = read(tmp, "state.md")
            self.assertEqual(text.count("updated_at:"), 1)
            self.assertIn("Second.", text)
            self.assertNotIn("First.", text)

    def test_secret_line_in_a_state_note_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "state", "Deploy key AKIAIOSFODNN7EXAMPLE is set.\nKeep this line.\n")
            write_memory(tmp, "file-change")
            text = read(tmp, "state.md")
            self.assertNotIn("AKIAIOSFODNN7EXAMPLE", text)
            self.assertIn("Keep this line.", text)

    def test_state_shows_in_recall(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "state", "Parser done.\n\n## Constraints\n- stdlib only\n")
            write_memory(tmp, "file-change")
            context = select_context(os.path.join(tmp, ".continuity"))
            self.assertIn("Parser done.", context)
            self.assertIn("stdlib only", context)

    def test_state_note_is_counted_in_the_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "state", "Summary.\n")
            write_memory(tmp, "file-change")
            sessions = os.path.join(tmp, ".continuity", "sessions")
            handoff = open(os.path.join(sessions, os.listdir(sessions)[0])).read()
            self.assertIn("1 state", handoff)


if __name__ == "__main__":
    unittest.main()
