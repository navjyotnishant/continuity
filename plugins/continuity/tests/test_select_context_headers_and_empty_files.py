"""tests/test_select_context_headers_and_empty_files.py — CONTINUI-18 US3
coverage.

Two more ways `lib/select_context.py`'s `_entries()` must NOT treat a
durable file as corrupted:

  - A bare `##` section header (e.g. `## Conventions` in learnings.md, per
    data-model.md) has no fields and no body of its own, so `_is_section_header()`
    must drop it silently -- no logged failure, same as if it were never
    there.
  - A durable file that exists but is empty (as CONTINUI-23's seed
    templates leave state.md's siblings until a first real entry lands)
    must read back as "no entries yet", not as an unreadable or corrupted
    file.
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.select_context import _entries, select_context


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


class TestSectionHeaderNotTreatedAsCorrupted(unittest.TestCase):
    def test_bare_section_header_is_not_counted_as_a_corrupted_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "learnings.md"),
                "# Learnings\n\n## Conventions\n\n"
                "## Learning: real entry\n\n"
                "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: learning\n```\n\n"
                "A genuine entry after the section header.\n",
            )

            entries = _entries(store, "learnings.md")

            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["heading"], "Learning: real entry")
            self.assertEqual(read_errors_log(store), "")

    def test_section_header_does_not_appear_in_injected_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "learnings.md"),
                "# Learnings\n\n## Conventions\n\n"
                "## Learning: real entry\n\n"
                "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: learning\n```\n\n"
                "A genuine entry after the section header.\n",
            )

            context = select_context(store)

            self.assertIn("## Recent learnings", context)
            self.assertIn("real entry", context)
            self.assertNotIn("Conventions", context)


class TestEmptyDurableFileIsNoEntriesNotAnError(unittest.TestCase):
    def test_empty_learnings_file_returns_no_entries_and_logs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(os.path.join(store, "learnings.md"), "")

            entries = _entries(store, "learnings.md")

            self.assertEqual(entries, [])
            self.assertEqual(read_errors_log(store), "")

    def test_empty_durable_file_injects_no_section_and_does_not_block_siblings(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(os.path.join(store, "decisions.md"), "")
            write(
                os.path.join(store, "learnings.md"),
                "## Learning: sibling still loads\n\n"
                "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: learning\n```\n\n"
                "Unaffected by decisions.md being empty.\n",
            )

            context = select_context(store)

            self.assertNotIn("## Recent decisions", context)
            self.assertIn("## Recent learnings", context)
            self.assertEqual(read_errors_log(store), "")


if __name__ == "__main__":
    unittest.main()
