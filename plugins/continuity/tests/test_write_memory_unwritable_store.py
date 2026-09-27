"""tests/test_write_memory_unwritable_store.py — CONTINUI-18 US3 coverage.

lib/write_memory.py must fail cleanly when `.continuity/` becomes
unwritable partway through a write: no partial durable file, no leftover
atomic-write temp debris, and — critically — the staged note that triggered
the write must survive the aborted attempt rather than being consumed,
since losing a staged note on a failed write would silently drop content
the user never got a chance to retry. Exercised directly against
`write_memory()` rather than through the subprocess CLI, since it is the
library function's own abort path under test.
"""

import os
import stat
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.write_memory import write_memory

# chmod is advisory for root, and native Windows ignores the POSIX mode bits
# outright, so the permission case proves nothing there.
PERMISSIONS_ENFORCED = os.name != "nt" and getattr(os, "geteuid", lambda: 1)() != 0


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


class RestoreMode:
    """chmod a path for the duration of a block, then put the mode back."""

    def __init__(self, path, mode):
        self.path = path
        self.mode = mode

    def __enter__(self):
        self.original = stat.S_IMODE(os.stat(self.path).st_mode)
        os.chmod(self.path, self.mode)
        return self

    def __exit__(self, *_exc):
        os.chmod(self.path, self.original)
        return False


def temp_debris(store):
    """Any `<target>.tmp.*` file an interrupted atomic write left behind."""
    found = []
    for root, _dirs, files in os.walk(store):
        found.extend(name for name in files if ".tmp." in name)
    return found


@unittest.skipUnless(PERMISSIONS_ENFORCED, "chmod is not enforced for this user/platform")
class TestWriteFailsCleanlyWhenStoreUnwritable(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.project = self.tmp.name
        self.store = os.path.join(self.project, ".continuity")
        self.staged = write(
            os.path.join(self.store, ".staged", "decision-20260912T140501Z-4242.md"),
            "# Staged while the store was still writable\n\nBody.\n",
        )

    def test_write_fails_cleanly_when_directory_becomes_unwritable_during_write(self):
        # r-x: the staged note is still listable and readable, but nothing
        # new (lock, durable file, handoff) can be created under the store.
        with RestoreMode(self.store, 0o500):
            handoff_path = write_memory(self.project, "explicit-checkpoint")

        self.assertIsNone(handoff_path)
        self.assertFalse(os.path.exists(os.path.join(self.store, "decisions.md")))
        self.assertEqual(
            temp_debris(self.store), [], "no partial file may be left behind"
        )

    def test_staged_notes_are_not_consumed_when_write_fails(self):
        with RestoreMode(self.store, 0o500):
            write_memory(self.project, "explicit-checkpoint")

        self.assertTrue(
            os.path.exists(self.staged),
            "an aborted write must not consume the staged note",
        )


if __name__ == "__main__":
    unittest.main()
