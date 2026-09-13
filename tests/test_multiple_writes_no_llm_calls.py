"""tests/test_multiple_writes_no_llm_calls.py — CONTINUI-12 (US2: Never
notice Continuity is running).

test_write_memory_basic.py's T021 coverage proves statically (via an AST
walk of the import graph) that the write path can never reach a
network-capable module. This complements that with a runtime guard over a
simulated long session: several background writes back to back — the kind
of volume real usage produces as PostToolUse/SessionEnd fire repeatedly —
each with `socket.socket` poisoned to raise if anything on the path ever
tries to open one. A session that got slower or costlier the longer it ran
would mean the writer was reaching out per call; here every call must
complete without ever touching the network primitive an LLM API call would
have to go through.
"""

import os
import socket
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib import write_memory  # noqa: E402  (path insert must run first)


class _ForbiddenSocket(socket.socket):
    def __init__(self, *args, **kwargs):
        raise AssertionError("write path opened a network socket")


def stage(project_root, kind, suffix, body="# Note\n\nBody.\n"):
    path = os.path.join(project_root, ".continuity", ".staged", "{}-{}.md".format(kind, suffix))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
    return path


class TestManyBackgroundWritesNeverTouchTheNetwork(unittest.TestCase):
    def test_repeated_writes_across_a_long_session_open_no_socket(self):
        trigger_kinds = ["file-change"] * 5 + ["git-diff"] * 3 + ["session-end"] * 2
        with tempfile.TemporaryDirectory() as project:
            with mock.patch("socket.socket", _ForbiddenSocket):
                for index, trigger_kind in enumerate(trigger_kinds):
                    stage(project, "decision", "20260912T1405{:02d}Z-{}".format(index, index))
                    handoff = write_memory.write_memory(project, trigger_kind)
                    self.assertIsNotNone(
                        handoff, "write #{} produced nothing to checkpoint".format(index)
                    )

    def test_a_run_with_nothing_staged_is_also_socket_free(self):
        # The no-op path (FR-011) is exercised just as often in a long
        # session as the writing path, and must be exactly as network-free.
        with tempfile.TemporaryDirectory() as project:
            with mock.patch("socket.socket", _ForbiddenSocket):
                for trigger_kind in ("file-change", "session-end", "git-diff"):
                    self.assertIsNone(write_memory.write_memory(project, trigger_kind))


if __name__ == "__main__":
    unittest.main()
