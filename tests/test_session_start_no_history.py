"""tests/test_session_start_no_history.py — SessionStart with no prior store.

contracts/hook-io-contract.md -> SessionStart, FR-007/FR-012: a project that
has never run Continuity has no `.continuity/` directory yet. The hook must
inject no context, must not create the directory itself (it is a read-only
operation), must log nothing, and must never surface an error to the
session — it just proceeds normally.
"""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

SESSION_START_HOOK = os.path.join(REPO_ROOT, "hooks", "session-start.py")

_SPEC = importlib.util.spec_from_file_location(
    "session_start", SESSION_START_HOOK
)
session_start = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(session_start)


class TestNoPriorHistoryInjectsNoContext(unittest.TestCase):
    def test_build_context_returns_empty_string_for_a_project_with_no_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(session_start.build_context(tmp), "")

    def test_hook_output_carries_no_additional_context_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"session_id": "s", "cwd": tmp}
            stdin = io.StringIO(json.dumps(payload))
            stdout = io.StringIO()
            with mock_stdio(stdin, stdout):
                self.assertEqual(session_start.main(), 0)

            output = json.loads(stdout.getvalue())
            self.assertNotIn(
                "additionalContext", output.get("hookSpecificOutput", {})
            )
            self.assertEqual(
                output["hookSpecificOutput"]["hookEventName"], "SessionStart"
            )

    def test_no_error_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"session_id": "s", "cwd": tmp}
            stdin = io.StringIO(json.dumps(payload))
            with mock_stdio(stdin, io.StringIO()):
                session_start.main()

            self.assertFalse(
                os.path.exists(os.path.join(tmp, ".continuity", "errors.log"))
            )


class TestNoPriorHistoryCreatesNothing(unittest.TestCase):
    def test_hook_does_not_create_the_continuity_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = {"session_id": "s", "cwd": tmp}
            stdin = io.StringIO(json.dumps(payload))
            with mock_stdio(stdin, io.StringIO()):
                session_start.main()

            self.assertFalse(os.path.isdir(os.path.join(tmp, ".continuity")))
            self.assertEqual(os.listdir(tmp), [])


class TestNoPriorHistorySessionProceedsNormally(unittest.TestCase):
    def test_hook_process_exits_zero_with_no_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, SESSION_START_HOOK],
                input=json.dumps({"session_id": "s", "cwd": tmp}),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            output = json.loads(result.stdout)
            self.assertNotIn(
                "additionalContext", output.get("hookSpecificOutput", {})
            )


class mock_stdio:
    """Swap sys.stdin/stdout for the duration of one hook invocation."""

    def __init__(self, stdin, stdout):
        self._stdin = stdin
        self._stdout = stdout

    def __enter__(self):
        self._orig_stdin, sys.stdin = sys.stdin, self._stdin
        self._orig_stdout, sys.stdout = sys.stdout, self._stdout

    def __exit__(self, *exc_info):
        sys.stdin = self._orig_stdin
        sys.stdout = self._orig_stdout


if __name__ == "__main__":
    unittest.main()
