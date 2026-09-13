"""tests/test_write_memory_titles.py — title/body derivation for CONTINUI-3 US1.

Covers the cases test_write_memory_basic.py's title/heading tests don't:
a headingless note's title comes from its opening words (bounded to 72
chars, dropping nothing from the body), and a body heading is demoted by
exactly two `#` levels (`##` -> `####`), not merely "not a new entry".
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


class TestTitleAndBodyDerivation(unittest.TestCase):
    def test_headingless_note_uses_opening_words_as_title(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_line = (
                "Switch the retention sweep to a daily cron instead of "
                "running it inline on every session start for good measure"
            )
            self.assertGreater(len(first_line), 72)
            stage(tmp, "learning", first_line + "\n\nThe inline sweep was blocking startup.\n")

            write_memory(tmp, "file-change")

            entries = _entries(os.path.join(tmp, ".continuity"), "learnings.md")
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["heading"], "Learning: " + first_line[:72].rstrip())
            body = "\n".join(entries[0]["body"])
            self.assertIn(first_line, body, "opening words must stay in the body too")
            self.assertIn("blocking startup", body)

    def test_body_heading_is_demoted_exactly_two_levels(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(
                tmp,
                "decision",
                "# Real entry\n\n# Also demoted\n\n## Not a second entry\n\nBody.\n",
            )

            write_memory(tmp, "file-change")

            decisions = read(os.path.join(tmp, ".continuity", "decisions.md"))
            self.assertIn("### Also demoted", decisions)
            self.assertIn("#### Not a second entry", decisions)
            self.assertNotIn("\n## Not a second entry", decisions)
            self.assertNotIn("\n# Also demoted", decisions)


if __name__ == "__main__":
    unittest.main()
