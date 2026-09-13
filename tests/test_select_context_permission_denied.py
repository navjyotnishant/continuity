"""tests/test_select_context_permission_denied.py — CONTINUI-18 US3 coverage.

lib/select_context.py's read path must degrade a single unreadable file
(`chmod 000`) exactly like a corrupted one (T027): the session still gets a
context block, the unreadable file's content never appears in it, its
failure is logged as `unreadable` (not `corrupted`), and a readable sibling
loads as if nothing were wrong. Exercised directly against `select_context`
rather than through the `session-start` hook subprocess, since the read
path itself — not the hook's stdin/stdout framing — is what has to survive
the permission error.
"""

import os
import stat
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.select_context import select_context

# chmod is advisory for root, and native Windows ignores the POSIX mode bits
# outright, so the permission case proves nothing there.
PERMISSIONS_ENFORCED = os.name != "nt" and getattr(os, "geteuid", lambda: 1)() != 0

VALID_LEARNING = (
    "## Learning: sibling file with no permission problem\n\n"
    "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: learning\n```\n\n"
    "Must still load when state.md is unreadable.\n"
)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def read_errors_log(store):
    path = os.path.join(store, "errors.log")
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as handle:
        return handle.read()


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


@unittest.skipUnless(PERMISSIONS_ENFORCED, "chmod is not enforced for this user/platform")
class TestUnreadableFilePermissionError(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = os.path.join(self.tmp.name, ".continuity")
        self.state = write(
            os.path.join(self.store, "state.md"),
            "# Project state\n\n```\nupdated_at: 2026-09-11T09:00:00Z\n```\n\n"
            "Unreadable content that must never be injected.\n",
        )
        write(os.path.join(self.store, "learnings.md"), VALID_LEARNING)

    def test_session_starts_successfully_with_file_permission_error(self):
        with RestoreMode(self.state, 0o000):
            context = select_context(self.store)

        self.assertIsInstance(context, str)

    def test_unreadable_file_is_logged_as_unreadable_operation_in_errors_log(self):
        with RestoreMode(self.state, 0o000):
            select_context(self.store)

        log = read_errors_log(self.store)
        fields = [part.strip() for part in log.rstrip("\n").split("|")]
        self.assertEqual(fields[1], "read-state")
        self.assertEqual(fields[2], "unreadable")

    def test_unreadable_files_content_does_not_appear_in_context(self):
        with RestoreMode(self.state, 0o000):
            context = select_context(self.store)

        self.assertNotIn("Unreadable content that must never be injected", context)
        self.assertNotIn("## State", context)

    def test_readable_files_load_normally_when_sibling_file_is_unreadable(self):
        with RestoreMode(self.state, 0o000):
            context = select_context(self.store)

        self.assertIn("## Recent learnings", context)
        self.assertIn("sibling file with no permission problem", context)


if __name__ == "__main__":
    unittest.main()
