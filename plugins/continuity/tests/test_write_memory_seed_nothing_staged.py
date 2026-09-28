"""tests/test_write_memory_seed_nothing_staged.py — CONTINUI-18 US3 coverage.

CONTINUI-23's `_seed_store()` runs only after `write_memory()` finds
something staged (FR-011): a trigger firing over a project with nothing
staged must create nothing at all, not even the four seed files, and not
even a bare `.continuity/` directory. Exercised directly at the lib level
(as opposed to tests/test_checkpoint_command.py's CLI-subprocess coverage
of the same rule) so the seeding call itself is proven never to run.
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.write_memory import SEED_FILES, write_memory


class TestNoStagedNotesMeansNoSeeding(unittest.TestCase):
    def test_missing_continuity_dir_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = write_memory(tmp, "file-change")

            self.assertIsNone(result)
            self.assertFalse(os.path.exists(os.path.join(tmp, ".continuity")))

    def test_empty_staged_dir_seeds_no_durable_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(os.path.join(store, ".staged"))

            result = write_memory(tmp, "file-change")

            self.assertIsNone(result)
            for name in SEED_FILES:
                self.assertFalse(
                    os.path.exists(os.path.join(store, name)),
                    "{} must not be seeded when nothing is staged".format(name),
                )
            self.assertFalse(os.path.exists(os.path.join(store, "sessions")))

    def test_staged_dir_with_only_non_md_files_seeds_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            staged = os.path.join(store, ".staged")
            os.makedirs(staged)
            with open(os.path.join(staged, "notes.txt"), "w", encoding="utf-8") as handle:
                handle.write("not a staged note per the .md contract\n")

            result = write_memory(tmp, "file-change")

            self.assertIsNone(result)
            for name in SEED_FILES:
                self.assertFalse(os.path.exists(os.path.join(store, name)))


if __name__ == "__main__":
    unittest.main()
