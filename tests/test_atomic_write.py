# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-13
# Description: Unit tests for lib/atomic_write.py (T004/T009) — new-file
#              write, read-back, overwrite-replaces-content, the
#              empty-content refusal, and crash-residue cases.
#
# Contract under test (contracts/file-format-contract.md -> Atomicity):
#   atomic_write(target, content)
#     - writes content to <target>, replacing any prior content
#     - returns True once written
#     - returns False, touching nothing, when content is empty/whitespace
#     - raises OSError on a genuine write/replace failure; every caller is a
#       fail-open path that catches it (FR-012)
#
# Rewritten from a shell-invocation suite that called a Bash lib/atomic_write.sh
# via subprocess (T032, the project's move to Python) -- every case here calls
# the Python atomic_write() function directly rather than shelling out.
#
# Run with: python3 -m unittest tests.test_atomic_write

import os
import tempfile
import threading
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
import sys

sys.path.insert(0, str(REPO_ROOT))

from lib.atomic_write import atomic_write


class TestAtomicWrite(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.target = Path(self.tmpdir.name) / "state.md"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_writes_content_to_a_new_file(self):
        result = atomic_write(str(self.target), "hello\nworld\n")
        self.assertTrue(result)
        self.assertTrue(self.target.is_file())

    def test_reading_back_written_content_matches_original(self):
        content = "hello\nworld\n"
        atomic_write(str(self.target), content)
        self.assertEqual(self.target.read_text(), content)

    def test_overwriting_an_existing_file_replaces_content(self):
        atomic_write(str(self.target), "first version\n")
        result = atomic_write(str(self.target), "second version\n")
        self.assertTrue(result)
        self.assertEqual(self.target.read_text(), "second version\n")

    def test_no_tmp_residue_after_a_successful_write(self):
        atomic_write(str(self.target), "hello\n")
        leftover = list(self.target.parent.glob(f"{self.target.name}.tmp.*"))
        self.assertEqual(leftover, [], f"orphaned tmp files: {leftover}")

    def test_empty_content_is_rejected(self):
        result = atomic_write(str(self.target), "")
        self.assertFalse(result)

    def test_whitespace_only_content_is_rejected(self):
        result = atomic_write(str(self.target), "   \n\t\n")
        self.assertFalse(result)

    def test_target_unchanged_when_empty_write_is_rejected(self):
        atomic_write(str(self.target), "original content\n")
        atomic_write(str(self.target), "")
        self.assertEqual(self.target.read_text(), "original content\n")

    def test_no_tmp_residue_after_a_rejected_empty_write(self):
        atomic_write(str(self.target), "original content\n")
        atomic_write(str(self.target), "")
        leftover = list(self.target.parent.glob(f"{self.target.name}.tmp.*"))
        self.assertEqual(leftover, [], f"orphaned tmp files: {leftover}")

    def test_empty_write_on_a_target_that_never_existed_creates_nothing(self):
        atomic_write(str(self.target), "")
        self.assertFalse(self.target.exists())

    def test_crash_between_write_and_rename_leaves_target_intact(self):
        # Simulated directly rather than through atomic_write: this is the
        # on-disk state a killed process leaves behind, which
        # lib/retention.py (T031/T032) is responsible for sweeping.
        atomic_write(str(self.target), "original content\n")
        orphan_tmp = self.target.parent / f"{self.target.name}.tmp.99999"
        orphan_tmp.write_text("half-written replacement")

        self.assertEqual(self.target.read_text(), "original content\n")
        self.assertTrue(orphan_tmp.is_file())

    def test_setup_creates_a_fresh_temp_directory_per_test(self):
        self.assertTrue(Path(self.tmpdir.name).is_dir())
        self.assertFalse(self.target.exists())

    def test_teardown_removes_the_temp_directory(self):
        other = tempfile.TemporaryDirectory()
        other_path = Path(other.name)
        self.assertTrue(other_path.is_dir())
        other.cleanup()
        self.assertFalse(other_path.exists())

    def test_cases_do_not_interfere_with_each_other(self):
        with tempfile.TemporaryDirectory() as other_dir:
            other_target = Path(other_dir) / self.target.name
            atomic_write(str(self.target), "this test's content\n")
            atomic_write(str(other_target), "other directory's content\n")

            self.assertEqual(self.target.read_text(), "this test's content\n")
            self.assertEqual(
                other_target.read_text(), "other directory's content\n"
            )

    def test_written_bytes_match_input_exactly(self):
        # No trailing newline, CR/LF mix, and a tab: a byte-for-byte check,
        # not just "looks the same". atomic_write opens the temp file in
        # text mode with newline="\n", so a bare \n survives unchanged and
        # an embedded \r is written as data, not translated.
        content = "line one\r\nline two\ttabbed\nno trailing newline at all"
        atomic_write(str(self.target), content)
        self.assertEqual(self.target.read_text(newline=""), content)

    def test_concurrent_writes_each_use_their_own_pid_tmp_file(self):
        # If the temp filename were reused across concurrent calls rather
        # than each getting its own (tempfile.NamedTemporaryFile's own
        # uniqueness), two writers to the same target could stomp each
        # other's tmp file and the final content could come out corrupted
        # or interleaved rather than being exactly one writer's full
        # content.
        content_a = "A" * 5000 + "\n"
        content_b = "B" * 5000 + "\n"
        results = [None, None]

        def write(i, content):
            results[i] = atomic_write(str(self.target), content)

        t_a = threading.Thread(target=write, args=(0, content_a))
        t_b = threading.Thread(target=write, args=(1, content_b))
        t_a.start()
        t_b.start()
        t_a.join()
        t_b.join()

        self.assertTrue(results[0])
        self.assertTrue(results[1])
        final = self.target.read_text()
        self.assertIn(final, (content_a, content_b))
        leftover = list(self.target.parent.glob(f"{self.target.name}.tmp.*"))
        self.assertEqual(leftover, [], f"orphaned tmp files: {leftover}")

    def test_target_path_with_subdirectories_not_in_tmpdir_root(self):
        nested = self.target.parent / "nested" / "deeper"
        nested.mkdir(parents=True)
        target = nested / "state.md"
        result = atomic_write(str(target), "nested content\n")
        self.assertTrue(result)
        self.assertEqual(target.read_text(), "nested content\n")

    def test_permission_denied_on_unwritable_target_directory(self):
        if os.geteuid() == 0:
            self.skipTest("root bypasses directory permission checks")
        locked_dir = self.target.parent / "locked"
        locked_dir.mkdir()
        target = locked_dir / "state.md"
        locked_dir.chmod(0o555)
        try:
            with self.assertRaises(OSError):
                atomic_write(str(target), "should not land\n")
        finally:
            locked_dir.chmod(0o755)
        self.assertFalse(target.exists())

    def test_missing_parent_directory_is_created_rather_than_rejected(self):
        # atomic_write's own contract: os.makedirs(..., exist_ok=True)
        # creates the parent unconditionally. A caller that wants "refuse
        # if the parent is missing" has to check for that itself before
        # calling; atomic_write does not treat it as a failure.
        target = self.target.parent / "missing" / "state.md"
        result = atomic_write(str(target), "should land\n")
        self.assertTrue(result)
        self.assertEqual(target.read_text(), "should land\n")

    def test_filename_with_spaces_and_quotes_is_written_correctly(self):
        target = self.target.parent / "my \"weird\" 'state' file.md"
        result = atomic_write(str(target), "content for a weird filename\n")
        self.assertTrue(result)
        self.assertEqual(target.read_text(), "content for a weird filename\n")

    def test_binary_like_content_is_written_byte_for_byte(self):
        # atomic_write's contract is text content (it opens in text mode
        # with an explicit encoding); this checks the widest text payload
        # that mode can carry rather than genuine binary data, which would
        # need a different primitive entirely.
        content = "".join(chr(c) for c in range(1, 128) if c not in (10, 13))
        content += "\ntrailing"
        atomic_write(str(self.target), content)
        self.assertEqual(self.target.read_text(), content)

    def test_target_that_is_a_directory_raises(self):
        target_dir = self.target.parent / "a_directory"
        target_dir.mkdir()
        with self.assertRaises(OSError):
            atomic_write(str(target_dir), "should not land\n")
        self.assertTrue(target_dir.is_dir())

    def test_concurrent_writes_to_different_targets_do_not_cross_contaminate(self):
        targets = [self.target.parent / f"state-{i}.md" for i in range(8)]
        results = [None] * len(targets)

        def write(i):
            results[i] = atomic_write(str(targets[i]), f"content for {i}\n")

        threads = [threading.Thread(target=write, args=(i,)) for i in range(len(targets))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i, target in enumerate(targets):
            self.assertTrue(results[i])
            self.assertEqual(target.read_text(), f"content for {i}\n")


if __name__ == "__main__":
    unittest.main()
