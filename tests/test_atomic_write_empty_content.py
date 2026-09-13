"""tests/test_atomic_write_empty_content.py — atomic_write's empty-content no-op.

lib/atomic_write.py's own docstring states a rule no existing test drives:
empty or whitespace-only content must return False and leave `target`
completely untouched (data-model.md's State Note rule — a trigger that
produced no meaningful summary must not silently wipe prior state). Every
existing atomic_write test uses real content, so a regression here — writing
an empty file over real prior state — would not fail anything already in
the suite.
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.atomic_write import atomic_write


class TestEmptyContentIsANoOp(unittest.TestCase):
    def test_empty_string_returns_false_and_does_not_create_the_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "state.md")

            self.assertFalse(atomic_write(target, ""))

            self.assertFalse(os.path.exists(target))

    def test_whitespace_only_content_returns_false_and_does_not_create_the_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "state.md")

            self.assertFalse(atomic_write(target, "   \n\t\n  "))

            self.assertFalse(os.path.exists(target))

    def test_whitespace_only_content_never_overwrites_existing_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "state.md")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("real prior state\n")

            self.assertFalse(atomic_write(target, "\n\n"))

            with open(target, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "real prior state\n")


if __name__ == "__main__":
    unittest.main()
