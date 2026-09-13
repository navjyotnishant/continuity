"""tests/test_select_context_corruption_us3.py — CONTINUI-18 US3 coverage.

"Keep working when memory breaks": a corrupted entry or a corrupted
state.md must not stop valid siblings from being injected, must be
recorded in errors.log per data-model.md's Failure Log Entry rule (a
count, never the raw text), and multiple corrupt entries in one file
collapse into a single logged count rather than one line each
(lib/select_context.py's _entries()).
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.select_context import select_context


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def read_errors_log(store):
    path = os.path.join(store, "errors.log")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class TestValidFilesStillInjectAroundOneCorruptFile(unittest.TestCase):
    def test_session_injects_context_from_valid_files_even_when_one_file_is_corrupted(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "decisions.md"),
                "## Decision: corrupted entry\n\nNo fenced metadata at all.\n",
            )
            write(
                os.path.join(store, "learnings.md"),
                "## Learning: os.replace() is atomic on Windows too\n\n"
                "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: learning\n```\n\n"
                "Same filesystem only.\n",
            )

            context = select_context(store)

            self.assertIn("## Recent learnings", context)
            self.assertIn("os.replace() is atomic on Windows too", context)
            self.assertNotIn("## Recent decisions", context)


class TestCorruptedEntryMissingCapturedAt(unittest.TestCase):
    def test_corrupted_entry_missing_captured_at_is_skipped_and_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "decisions.md"),
                "## Decision: missing its captured_at\n\n"
                "```\ncategory: decision\n```\n\n"
                "Should be skipped.\n",
            )

            select_context(store)

            log = read_errors_log(store)
            fields = [part.strip() for part in log.rstrip("\n").split("|")]
            self.assertEqual(fields[1], "read-decisions")
            self.assertEqual(fields[2], "corrupted")
            self.assertIn("1 of 1 entries skipped as invalid", fields[3])

    def test_corrupted_entry_is_not_included_in_injected_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "decisions.md"),
                "## Decision: missing its captured_at\n\n"
                "```\ncategory: decision\n```\n\n"
                "Should be skipped.\n",
            )

            context = select_context(store)

            self.assertNotIn("missing its captured_at", context)
            self.assertNotIn("Should be skipped", context)


class TestCorruptedStateMd(unittest.TestCase):
    def test_corrupted_state_md_missing_updated_at_is_logged_in_errors_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "state.md"),
                "# Project State\n\n```\ncategory: state\n```\n\n"
                "No updated_at field here.\n",
            )

            select_context(store)

            log = read_errors_log(store)
            fields = [part.strip() for part in log.rstrip("\n").split("|")]
            self.assertEqual(fields[1], "read-state")
            self.assertEqual(fields[2], "corrupted")
            self.assertIn("no parseable updated_at", fields[3])

    def test_corrupted_state_md_causes_no_state_injected_in_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "state.md"),
                "# Project State\n\n```\ncategory: state\n```\n\n"
                "No updated_at field here.\n",
            )
            write(
                os.path.join(store, "learnings.md"),
                "## Learning: sibling still loads\n\n"
                "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: learning\n```\n\n"
                "Unaffected by state.md's corruption.\n",
            )

            context = select_context(store)

            self.assertNotIn("## State", context)
            self.assertNotIn("No updated_at field here", context)
            self.assertIn("## Recent learnings", context)


class TestMultipleCorruptEntriesCountedTogether(unittest.TestCase):
    def test_multiple_corrupted_entries_in_one_file_are_counted_and_logged_together(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "decisions.md"),
                "## Decision: first corrupt entry\n\n"
                "```\ncategory: decision\n```\n\nMissing captured_at.\n\n"
                "## Decision: second corrupt entry\n\n"
                "```\ncaptured_at: 2026-09-10T10:00:00Z\n```\n\nMissing category.\n\n"
                "## Decision: valid sibling\n\n"
                "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: decision\n```\n\n"
                "Loads fine.\n",
            )

            select_context(store)

            log = read_errors_log(store)
            lines = log.splitlines()
            decisions_lines = [line for line in lines if "read-decisions" in line]
            self.assertEqual(
                len(decisions_lines),
                1,
                "two corrupt entries in one file must produce one logged count, "
                "not one line per entry",
            )
            self.assertIn("2 of 3 entries skipped as invalid", decisions_lines[0])


class TestErrorsLogNeverCarriesRawContent(unittest.TestCase):
    def test_errors_log_never_contains_raw_entry_text_or_file_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            secret_body = "super-secret-body-text-should-never-be-logged"
            write(
                os.path.join(store, "decisions.md"),
                "## Decision: corrupt entry with sensitive body\n\n"
                "```\ncategory: decision\n```\n\n" + secret_body + "\n",
            )
            write(
                os.path.join(store, "state.md"),
                "# Project State\n\n```\ncategory: state\n```\n\n"
                + secret_body
                + "\n",
            )

            select_context(store)

            log = read_errors_log(store)
            self.assertNotIn(secret_body, log)
            self.assertNotIn("corrupt entry with sensitive body", log)


if __name__ == "__main__":
    unittest.main()
