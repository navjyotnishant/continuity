"""tests/test_write_memory_permission_recovery.py — CONTINUI-18 US3 coverage.

A store whose directory permissions block every write (seeding,
lib/lock.py's lock_acquire, and the append itself) must fail open with no
exception (FR-012) and no partial file -- and once permissions are restored,
the very next write must succeed normally, seeding and consolidating as if
the earlier failure had never happened. Mirrors the chmod pattern already
used in tests/test_lock_permission_denied.py.
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.write_memory import write_memory


def stage(project_root, kind, body, suffix):
    path = os.path.join(
        project_root, ".continuity", ".staged", "{}-{}.md".format(kind, suffix)
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@unittest.skipIf(os.name == "nt", "chmod-based permission denial is POSIX-specific")
class TestWriteSucceedsAfterPermissionsRestored(unittest.TestCase):
    def test_write_fails_open_while_store_is_unwritable_then_succeeds_once_restored(
        self,
    ):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            stage(tmp, "decision", "# First attempt\n\nBlocked by permissions.\n", "1")

            os.chmod(store, 0o500)  # read+execute, no write
            try:
                result = write_memory(tmp, "file-change")
            finally:
                os.chmod(store, 0o700)

            self.assertIsNone(result, "a blocked write must fail open, not raise")
            self.assertFalse(os.path.exists(os.path.join(store, "decisions.md")))

            stage(tmp, "decision", "# Second attempt\n\nWorks now.\n", "2")
            result = write_memory(tmp, "file-change")

            self.assertIsNotNone(result, "the next write must succeed normally")
            decisions = read(os.path.join(store, "decisions.md"))
            self.assertIn("Second attempt", decisions)
            self.assertIn("Works now.", decisions)


if __name__ == "__main__":
    unittest.main()
