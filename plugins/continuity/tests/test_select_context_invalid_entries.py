"""tests/test_select_context_invalid_entries.py — entry validity beyond captured_at.

tests/test_select_context.py's malformed-entry case only drives one of
_is_valid()'s two required fields (a missing `captured_at`). A `category`-less
entry, and a task entry whose `status` is not one of active/blocked/done,
exercise the other branches — nothing existing proves the code even reaches
them.
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


class TestEntryMissingCategoryIsSkipped(unittest.TestCase):
    def test_entry_without_category_field_is_dropped_sibling_still_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "decisions.md"),
                "## Decision: missing its category\n\n"
                "```\ncaptured_at: 2026-09-10T10:00:00Z\n```\n\n"
                "Should be skipped.\n\n"
                "## Decision: valid sibling\n\n"
                "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: decision\n```\n\n"
                "Should still load.\n",
            )

            context = select_context(store)

            self.assertIn("valid sibling", context)
            self.assertNotIn("missing its category", context)


class TestTaskWithInvalidStatusIsSkipped(unittest.TestCase):
    def test_task_entry_with_unrecognized_status_is_dropped_sibling_still_loads(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write(
                os.path.join(store, "tasks.md"),
                "## Task: bogus status value\n\n"
                "```\ncaptured_at: 2026-09-10T10:00:00Z\ncategory: task\n"
                "status: in-progress\n```\n\n"
                "Should be skipped -- not one of active/blocked/done.\n\n"
                "## Task: valid sibling\n\n"
                "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: task\n"
                "status: active\n```\n\n"
                "Should still load.\n",
            )

            context = select_context(store)

            self.assertIn("valid sibling", context)
            self.assertNotIn("bogus status value", context)


if __name__ == "__main__":
    unittest.main()
