"""tests/test_select_context_handoff_corruption.py — CONTINUI-18 US3 coverage.

A corrupted `sessions/<timestamp>-<pid>.md` handoff file must degrade the
same way any other durable file does (FR-013): logged and treated as
absent, never surfaced in the injected context, and never allowed to stop
other sections from loading. Uses the same chmod-000 permission pattern as
tests/test_select_context_permission_denied.py, scoped to the one nested
file lib/select_context.py's `_operation()` maps to the shared
`read-handoff` label.
"""

import os
import stat
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.select_context import select_context

PERMISSIONS_ENFORCED = os.name != "nt" and getattr(os, "geteuid", lambda: 1)() != 0

VALID_LEARNING = (
    "## Learning: sibling file with no permission problem\n\n"
    "```\ncaptured_at: 2026-09-11T10:00:00Z\ncategory: learning\n```\n\n"
    "Must still load when the handoff file is unreadable.\n"
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
class TestCorruptedHandoffFileInSessionsDir(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = os.path.join(self.tmp.name, ".continuity")
        self.handoff = write(
            os.path.join(self.store, "sessions", "20260911T100000Z-1111.md"),
            "```\ncaptured_at: 2026-09-11T10:00:00Z\ntrigger: file-change\n```\n\n"
            "Content that must never be injected once unreadable.\n",
        )
        write(os.path.join(self.store, "learnings.md"), VALID_LEARNING)

    def test_session_starts_successfully_with_corrupted_handoff_file(self):
        with RestoreMode(self.handoff, 0o000):
            context = select_context(self.store)

        self.assertIsInstance(context, str)

    def test_corrupted_handoff_is_logged_as_unreadable_and_treated_as_absent(self):
        with RestoreMode(self.handoff, 0o000):
            context = select_context(self.store)

        log = read_errors_log(self.store)
        fields = [part.strip() for part in log.rstrip("\n").split("|")]
        self.assertEqual(fields[1], "read-handoff")
        self.assertEqual(fields[2], "unreadable")
        self.assertNotIn("## Last handoff", context)
        self.assertNotIn(
            "Content that must never be injected once unreadable", context
        )

    def test_sibling_sections_still_load_when_handoff_is_corrupted(self):
        with RestoreMode(self.handoff, 0o000):
            context = select_context(self.store)

        self.assertIn("## Recent learnings", context)
        self.assertIn("sibling file with no permission problem", context)


if __name__ == "__main__":
    unittest.main()
