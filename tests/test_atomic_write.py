"""tests/test_atomic_write.py — lib/atomic_write.py's crash-safety contract
(contracts/file-format-contract.md -> Atomicity).

A reader must never observe a half-written file: content lands in a
`<target basename>.tmp.*` file in the same directory as `target`, and only
`os.replace()` makes it visible at `target`. These tests check that shape
directly, then simulate a killed process to prove a crash mid-write leaves
only the `.tmp.*` orphan behind and never touches the original target.
"""

import glob
import os
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.atomic_write import atomic_write


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class TestAtomicWriteShape(unittest.TestCase):
    def test_writes_to_a_same_directory_tmp_file_then_replaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "decisions.md")

            with mock.patch("lib.atomic_write.os.replace", wraps=os.replace) as replace:
                self.assertTrue(atomic_write(target, "content\n"))

                replace.assert_called_once()
                source, destination = replace.call_args.args
                self.assertEqual(destination, target)
                self.assertEqual(os.path.dirname(source), tmp)
                self.assertTrue(
                    os.path.basename(source).startswith("decisions.md.tmp."),
                    os.path.basename(source),
                )

            self.assertEqual(read(target), "content\n")
            # The temp file is gone once os.replace has moved it into place.
            self.assertEqual(glob.glob(os.path.join(tmp, "decisions.md.tmp.*")), [])


class TestAtomicWriteCrashRecovery(unittest.TestCase):
    def test_a_kill_mid_write_leaves_a_tmp_orphan_and_target_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "decisions.md")
            with open(target, "w", encoding="utf-8") as handle:
                handle.write("original content\n")

            script = (
                "import os, signal, sys\n"
                "sys.path.insert(0, {repo!r})\n"
                "from lib import atomic_write as aw\n"
                "def kill_before_replace(src, dst):\n"
                "    os.kill(os.getpid(), signal.SIGKILL)\n"
                "aw.os.replace = kill_before_replace\n"
                "aw.atomic_write(sys.argv[1], 'new content\\n')\n"
            ).format(repo=REPO_ROOT)

            result = subprocess.run(
                [sys.executable, "-c", script, target],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

            self.assertEqual(
                result.returncode, -signal.SIGKILL, "the child must have been killed"
            )
            self.assertEqual(
                read(target), "original content\n", "a crashed write must not touch target"
            )

            orphans = glob.glob(os.path.join(tmp, "decisions.md.tmp.*"))
            self.assertEqual(len(orphans), 1, "the crash must leave exactly one tmp orphan")
            self.assertEqual(read(orphans[0]), "new content\n")


if __name__ == "__main__":
    unittest.main()
