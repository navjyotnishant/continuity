"""tests/test_atomic_write_no_debris.py — CONTINUI-18 US3 coverage.

lib/atomic_write.py writes into a `<target basename>.tmp.*` file in the same
directory, then `os.replace()`s it onto `target`. When that replace fails,
the module unlinks the temp file before re-raising (its own `except OSError`
branch) — so a failed write must never leave `.tmp.*` crash debris behind for
lib/retention.py to have to sweep up later. Forced here by pointing `target`
at an existing directory, which makes `os.replace()` fail on every platform
without needing root or an unwritable filesystem.
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.atomic_write import atomic_write


def tmp_debris(directory):
    return [name for name in os.listdir(directory) if ".tmp." in name]


class TestNoTmpDebrisAfterFailedWrite(unittest.TestCase):
    def test_failed_replace_raises_and_leaves_no_tmp_file_behind(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A directory in place of the intended target: os.replace() can
            # never put a file there, so the replace step itself fails.
            target = os.path.join(tmp, "state.md")
            os.makedirs(target)

            with self.assertRaises(OSError):
                atomic_write(target, "some content\n")

            self.assertEqual(
                tmp_debris(tmp),
                [],
                "a failed atomic_write must not leave its .tmp.* file behind",
            )

    def test_target_directory_itself_is_untouched_by_the_failed_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "state.md")
            os.makedirs(target)

            with self.assertRaises(OSError):
                atomic_write(target, "some content\n")

            self.assertTrue(os.path.isdir(target))
            self.assertEqual(os.listdir(target), [])


if __name__ == "__main__":
    unittest.main()
