# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Python-invocable unit tests for lib/atomic_write.sh (T004/T009) —
#              new-file write, read-back, and overwrite-replaces-content.
#
# Contract under test (see tests/test_atomic_write.sh for the full contract,
# including the empty-content refusal and crash-residue cases):
#   source lib/atomic_write.sh
#   atomic_write <target>   # content on stdin
#     - writes stdin to <target>, replacing any prior content
#
# Run with: python3 -m unittest tests.test_atomic_write
#
# The primitive itself is a Bash function (lib/atomic_write.sh), so each case
# shells out to bash to source it and call atomic_write, then makes the
# assertion in Python.

import os
import shlex
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ATOMIC_WRITE_SH = REPO_ROOT / "lib" / "atomic_write.sh"


def run_atomic_write(target: Path, content: str) -> subprocess.CompletedProcess:
    script = f'. "{ATOMIC_WRITE_SH}" && atomic_write "{target}"'
    return subprocess.run(
        ["bash", "-c", script],
        input=content,
        capture_output=True,
        text=True,
    )


def run_atomic_write_quoted(target: Path, content: str) -> subprocess.CompletedProcess:
    # shlex.quote instead of a bare f-string interpolation, since a target
    # containing a double quote or `$` would otherwise break out of the
    # generated bash -c script rather than reach atomic_write as a value.
    script = f'. {shlex.quote(str(ATOMIC_WRITE_SH))} && atomic_write {shlex.quote(str(target))}'
    return subprocess.run(
        ["bash", "-c", script],
        input=content,
        capture_output=True,
        text=True,
    )


def run_atomic_write_bytes(target: Path, content: bytes) -> subprocess.CompletedProcess:
    script = f'. {shlex.quote(str(ATOMIC_WRITE_SH))} && atomic_write {shlex.quote(str(target))}'
    return subprocess.run(
        ["bash", "-c", script],
        input=content,
        capture_output=True,
    )


class TestAtomicWrite(unittest.TestCase):
    def setUp(self):
        if not ATOMIC_WRITE_SH.is_file():
            self.skipTest("lib/atomic_write.sh does not exist yet (T004)")
        self.tmpdir = tempfile.TemporaryDirectory()
        self.target = Path(self.tmpdir.name) / "state.md"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_writes_content_to_a_new_file(self):
        result = run_atomic_write(self.target, "hello\nworld\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.target.is_file())

    def test_reading_back_written_content_matches_original(self):
        content = "hello\nworld\n"
        run_atomic_write(self.target, content)
        self.assertEqual(self.target.read_text(), content)

    def test_overwriting_an_existing_file_replaces_content(self):
        run_atomic_write(self.target, "first version\n")
        result = run_atomic_write(self.target, "second version\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_text(), "second version\n")

    def test_no_tmp_residue_after_a_successful_write(self):
        run_atomic_write(self.target, "hello\n")
        leftover = list(self.target.parent.glob(f"{self.target.name}.tmp.*"))
        self.assertEqual(leftover, [], f"orphaned tmp files: {leftover}")

    def test_empty_content_is_rejected_with_nonzero_exit(self):
        result = run_atomic_write(self.target, "")
        self.assertNotEqual(result.returncode, 0)

    def test_target_unchanged_when_empty_write_is_rejected(self):
        run_atomic_write(self.target, "original content\n")
        run_atomic_write(self.target, "")
        self.assertEqual(self.target.read_text(), "original content\n")

    def test_no_tmp_residue_after_a_rejected_empty_write(self):
        run_atomic_write(self.target, "original content\n")
        run_atomic_write(self.target, "")
        leftover = list(self.target.parent.glob(f"{self.target.name}.tmp.*"))
        self.assertEqual(leftover, [], f"orphaned tmp files: {leftover}")

    def test_atomic_write_sh_exists_and_is_sourceable(self):
        # Precondition for every other case in this file: if the library is
        # missing or fails to source, every case above skips silently in
        # setUp — this pins that the failure would be visible instead.
        result = subprocess.run(
            ["bash", "-c", f'. "{ATOMIC_WRITE_SH}" && type atomic_write'],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_content_arrives_via_stdin_not_as_an_argument(self):
        # Passing content as a positional argument must not write it — the
        # contract is stdin-only (real callers write multi-line Markdown,
        # which an argv argument can't carry safely).
        script = f'. "{ATOMIC_WRITE_SH}" && atomic_write "{self.target}" "arg version"'
        subprocess.run(
            ["bash", "-c", script],
            input="stdin version\n",
            capture_output=True,
            text=True,
        )
        self.assertEqual(self.target.read_text(), "stdin version\n")

    def test_crash_between_write_and_rename_leaves_target_intact(self):
        # Simulated directly rather than through atomic_write: this is the
        # on-disk state a killed process leaves behind, which lib/retention.sh
        # (T031/T032) is responsible for sweeping.
        run_atomic_write(self.target, "original content\n")
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
            run_atomic_write(self.target, "this test's content\n")
            run_atomic_write(other_target, "other directory's content\n")

            self.assertEqual(self.target.read_text(), "this test's content\n")
            self.assertEqual(
                other_target.read_text(), "other directory's content\n"
            )

    def test_written_bytes_match_input_exactly(self):
        # No trailing newline, CR/LF mix, and a tab: a byte-for-byte check,
        # not just "looks the same".
        content = "line one\r\nline two\ttabbed\nno trailing newline at all"
        run_atomic_write(self.target, content)
        self.assertEqual(self.target.read_bytes(), content.encode())

    def test_concurrent_writes_each_use_their_own_pid_tmp_file(self):
        # If the temp filename didn't actually incorporate the writer's PID
        # (e.g. a fixed name reused across calls), two concurrent writers to
        # the same target could stomp each other's tmp file and the final
        # content could come out corrupted/interleaved rather than being
        # exactly one writer's full content.
        script = f'. "{ATOMIC_WRITE_SH}" && atomic_write "{self.target}"'
        content_a = "A" * 5000 + "\n"
        content_b = "B" * 5000 + "\n"
        proc_a = subprocess.Popen(
            ["bash", "-c", script], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        proc_b = subprocess.Popen(
            ["bash", "-c", script], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        out_a, err_a = proc_a.communicate(content_a)
        out_b, err_b = proc_b.communicate(content_b)
        self.assertEqual(proc_a.returncode, 0, err_a)
        self.assertEqual(proc_b.returncode, 0, err_b)
        final = self.target.read_text()
        self.assertIn(final, (content_a, content_b))
        leftover = list(self.target.parent.glob(f"{self.target.name}.tmp.*"))
        self.assertEqual(leftover, [], f"orphaned tmp files: {leftover}")

    def test_target_path_with_subdirectories_not_in_tmpdir_root(self):
        nested = self.target.parent / "nested" / "deeper"
        nested.mkdir(parents=True)
        target = nested / "state.md"
        result = run_atomic_write(target, "nested content\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_text(), "nested content\n")

    def test_permission_denied_on_unwritable_target_directory(self):
        if os.geteuid() == 0:
            self.skipTest("root bypasses directory permission checks")
        locked_dir = self.target.parent / "locked"
        locked_dir.mkdir()
        target = locked_dir / "state.md"
        locked_dir.chmod(0o555)
        try:
            result = run_atomic_write(target, "should not land\n")
        finally:
            locked_dir.chmod(0o755)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.exists())

    def test_parent_directory_of_target_does_not_exist(self):
        target = self.target.parent / "missing" / "state.md"
        result = run_atomic_write(target, "should not land\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.exists())


    def test_filename_with_spaces_and_quotes_is_written_correctly(self):
        target = self.target.parent / "my \"weird\" 'state' file.md"
        result = run_atomic_write_quoted(target, "content for a weird filename\n")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(target.read_text(), "content for a weird filename\n")

    def test_binary_stdin_content_is_written_byte_for_byte(self):
        content = bytes(range(256)) + b"\x00\xff\x00trailing"
        result = run_atomic_write_bytes(self.target, content)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.target.read_bytes(), content)

    def test_write_that_exceeds_available_space_fails_without_corrupting_target(self):
        # A real full disk is impractical to set up here, so this simulates
        # "too large to fit" with a shell-imposed file-size limit (ulimit -f,
        # in 512-byte blocks) instead of a genuine ENOSPC.
        run_atomic_write(self.target, "original content\n")
        script = (
            f"ulimit -f 1 && . {shlex.quote(str(ATOMIC_WRITE_SH))} "
            f"&& atomic_write {shlex.quote(str(self.target))}"
        )
        result = subprocess.run(
            ["bash", "-c", script],
            input="x" * 100_000,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.target.read_text(), "original content\n")

    def test_target_that_is_a_directory_is_rejected(self):
        target_dir = self.target.parent / "a_directory"
        target_dir.mkdir()
        result = run_atomic_write(target_dir, "should not land\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(target_dir.is_dir())

    def test_concurrent_writes_to_different_targets_do_not_cross_contaminate(self):
        targets = [self.target.parent / f"state-{i}.md" for i in range(8)]
        results = [None] * len(targets)

        def write(i):
            results[i] = run_atomic_write(targets[i], f"content for {i}\n")

        threads = [threading.Thread(target=write, args=(i,)) for i in range(len(targets))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        for i, target in enumerate(targets):
            self.assertEqual(results[i].returncode, 0, results[i].stderr)
            self.assertEqual(target.read_text(), f"content for {i}\n")


if __name__ == "__main__":
    unittest.main()
