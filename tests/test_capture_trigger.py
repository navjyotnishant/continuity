"""tests/test_capture_trigger.py — hooks/capture-trigger.py's classification.

contracts/hook-io-contract.md's PostToolUse rule: a whitespace-only edit and
a non-"git" Bash call are legitimate no-ops (no trigger, no writer spawned,
nothing logged); a real edit or a git-diff-bearing "git" Bash call is a
signal that launches the detached writer.
"""

import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

_SPEC = importlib.util.spec_from_file_location(
    "capture_trigger", os.path.join(REPO_ROOT, "hooks", "capture-trigger.py")
)
capture_trigger = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(capture_trigger)


class TestClassifyEditWhitespaceOnly(unittest.TestCase):
    def test_edit_with_whitespace_only_change_produces_no_trigger(self):
        payload = {
            "tool_name": "Edit",
            "tool_input": {
                "edits": [{"old_string": "foo\n  bar", "new_string": "foo\nbar"}]
            },
        }
        self.assertIsNone(capture_trigger.classify(payload))

    def test_write_with_whitespace_only_change_produces_no_trigger(self):
        payload = {"tool_name": "Write", "tool_input": {"content": "   \n\t \n"}}
        self.assertIsNone(capture_trigger.classify(payload))

    def test_whitespace_only_edit_spawns_no_writer_and_logs_nothing(self):
        with mock.patch.object(capture_trigger, "launch_writer") as launch, mock.patch.object(
            capture_trigger, "_log"
        ) as log:
            payload = {
                "cwd": "/tmp/project",
                "tool_name": "Write",
                "tool_input": {"content": "   \n"},
            }
            stdin = io.StringIO(json.dumps(payload))
            with mock.patch.object(sys, "stdin", stdin):
                self.assertEqual(capture_trigger.main(), 0)
            launch.assert_not_called()
            log.assert_not_called()


class TestClassifyEditNonWhitespace(unittest.TestCase):
    def test_edit_with_non_whitespace_change_produces_file_change_trigger(self):
        payload = {
            "tool_name": "Edit",
            "tool_input": {
                "edits": [{"old_string": "foo", "new_string": "bar"}]
            },
        }
        self.assertEqual(capture_trigger.classify(payload), "file-change")

    def test_non_whitespace_edit_spawns_the_writer(self):
        with mock.patch.object(capture_trigger, "launch_writer") as launch:
            payload = {
                "cwd": "/tmp/project",
                "tool_name": "Edit",
                "tool_input": {"edits": [{"old_string": "foo", "new_string": "bar"}]},
            }
            stdin = io.StringIO(json.dumps(payload))
            with mock.patch.object(sys, "stdin", stdin):
                self.assertEqual(capture_trigger.main(), 0)
            launch.assert_called_once_with("/tmp/project", "file-change")


class TestClassifyBashGitDiff(unittest.TestCase):
    def test_bash_git_with_non_whitespace_diff_produces_git_diff_trigger(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": "/repo"}
        with mock.patch.object(capture_trigger, "_has_non_whitespace_diff", return_value=True):
            self.assertEqual(capture_trigger.classify(payload), "git-diff")


class TestClassifyBashNotGit(unittest.TestCase):
    def test_bash_call_not_containing_git_produces_no_trigger(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}, "cwd": "/repo"}
        self.assertIsNone(capture_trigger.classify(payload))


class TestClassifyBashGitWhitespaceOnly(unittest.TestCase):
    def test_bash_git_with_only_whitespace_diff_produces_no_trigger(self):
        payload = {"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": "/repo"}
        with mock.patch.object(capture_trigger, "_has_non_whitespace_diff", return_value=False):
            self.assertIsNone(capture_trigger.classify(payload))


class TestMissingOrInvalidPayload(unittest.TestCase):
    def test_missing_payload_produces_no_trigger_and_exits_successfully(self):
        with mock.patch.object(capture_trigger, "launch_writer") as launch:
            with mock.patch.object(sys, "stdin", io.StringIO("")):
                self.assertEqual(capture_trigger.main(), 0)
            launch.assert_not_called()

    def test_invalid_json_payload_produces_no_trigger_and_exits_successfully(self):
        with mock.patch.object(capture_trigger, "launch_writer") as launch:
            with mock.patch.object(sys, "stdin", io.StringIO("{not json")):
                self.assertEqual(capture_trigger.main(), 0)
            launch.assert_not_called()

    def test_payload_missing_cwd_produces_no_trigger_and_exits_successfully(self):
        with mock.patch.object(capture_trigger, "launch_writer") as launch:
            payload = {"tool_name": "Edit", "tool_input": {}}
            with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
                self.assertEqual(capture_trigger.main(), 0)
            launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
