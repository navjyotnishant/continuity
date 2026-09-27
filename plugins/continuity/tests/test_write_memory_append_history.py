"""tests/test_write_memory_append_history.py — append-only history preservation.

contracts/file-format-contract.md: decisions.md/tasks.md/learnings.md are
append-only, one `## <Heading>: <title>` entry per note, separated by a
blank line. Each checkpoint run must add its entries without disturbing an
earlier run's — every prior entry stays individually parseable, entries
keep the order they were written in, and the blank-line separator between
entries survives every append.
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.select_context import _entries
from lib.write_memory import write_memory
from tests.test_write_memory_basic import read, stage


class TestSecondDecisionAppended(unittest.TestCase):
    def test_second_decision_appended_after_first_both_remain_parseable(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# First decision\n\nChose plain files.\n")
            write_memory(tmp, "file-change")

            stage(
                tmp,
                "decision",
                "# Second decision\n\nChose append-only entries.\n",
                suffix="20260912T140510Z-4242",
            )
            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            entries = _entries(store, "decisions.md")
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["heading"], "Decision: First decision")
            self.assertEqual(entries[1]["heading"], "Decision: Second decision")
            self.assertIn("Chose plain files.", "\n".join(entries[0]["body"]))
            self.assertIn("Chose append-only entries.", "\n".join(entries[1]["body"]))
            for entry in entries:
                self.assertEqual(entry["fields"]["category"], "decision")
                self.assertTrue(entry["fields"]["captured_at"].endswith("Z"))


class TestMultipleTaskAppendsPreserveOrder(unittest.TestCase):
    def test_three_task_appends_stay_in_original_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            for index, title in enumerate(["Alpha", "Beta", "Gamma"]):
                stage(
                    tmp,
                    "task",
                    "# {}\n\nBody for {}.\n".format(title, title),
                    suffix="20260912T14051{}Z-4242".format(index),
                )
                write_memory(tmp, "file-change")

            entries = _entries(
                os.path.join(tmp, ".continuity"), "tasks.md", require_status=True
            )
            self.assertEqual(
                [entry["heading"] for entry in entries],
                ["Task: Alpha", "Task: Beta", "Task: Gamma"],
            )
            for entry in entries:
                self.assertEqual(entry["fields"]["status"], "active")


class TestMultipleLearningAppendsPreserveOrder(unittest.TestCase):
    def test_three_learning_appends_stay_in_original_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            for index, title in enumerate(["One", "Two", "Three"]):
                stage(
                    tmp,
                    "learning",
                    "# {}\n\nBody for {}.\n".format(title, title),
                    suffix="20260912T14052{}Z-4242".format(index),
                )
                write_memory(tmp, "file-change")

            entries = _entries(os.path.join(tmp, ".continuity"), "learnings.md")
            self.assertEqual(
                [entry["heading"] for entry in entries],
                ["Learning: One", "Learning: Two", "Learning: Three"],
            )


class TestBlankLineSeparatorsSurviveAppending(unittest.TestCase):
    def test_blank_line_separates_every_pair_of_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "learning", "# First\n\nBody one.\n")
            write_memory(tmp, "file-change")
            stage(tmp, "learning", "# Second\n\nBody two.\n", suffix="20260912T140530Z-1")
            write_memory(tmp, "file-change")
            stage(tmp, "learning", "# Third\n\nBody three.\n", suffix="20260912T140531Z-1")
            write_memory(tmp, "file-change")

            text = read(os.path.join(tmp, ".continuity", "learnings.md"))
            headings = [
                index
                for index, line in enumerate(text.splitlines())
                if line.startswith("## ")
            ]
            self.assertEqual(len(headings), 3)

            lines = text.splitlines()
            for start, end in zip(headings, headings[1:]):
                between = lines[start:end]
                self.assertTrue(
                    any(not line.strip() for line in between),
                    "no blank separator between entries starting at lines "
                    "{} and {}".format(start, end),
                )


if __name__ == "__main__":
    unittest.main()
