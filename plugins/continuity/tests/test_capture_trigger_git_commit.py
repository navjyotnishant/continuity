"""tests/test_capture_trigger_git_commit.py — CONTINUI-12 (US2: Never notice
Continuity is running).

hooks/capture-trigger.py's classify() special-cases a `git commit` Bash
command: it returns "git-diff" unconditionally, without consulting
`_has_non_whitespace_diff` (capture-trigger.py:40-41). That is a real branch
with no coverage in the rest of the suite — every existing Bash test either
mocks `_has_non_whitespace_diff` directly (bypassing the commit branch) or
uses a non-git command. Right after a commit the working tree is typically
clean, so if this special case ever regressed to falling through to the
generic diff check, a Bash("git commit ...") call would silently stop being
a meaningful-change signal — exactly the class of memory-write commit the
plugin exists to capture.

This also covers the mirror negative case: a non-commit git command with no
non-whitespace diff must NOT trigger, proving the special case is scoped to
`git commit` rather than loosening the rule for git commands generally.
"""

import io
import json
import os
import sys
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

import importlib.util

CAPTURE_TRIGGER_SRC = os.path.join(REPO_ROOT, "hooks", "capture-trigger.py")
_SPEC = importlib.util.spec_from_file_location("capture_trigger_git_commit", CAPTURE_TRIGGER_SRC)
capture_trigger = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(capture_trigger)


def run_main(payload):
    with mock.patch.object(capture_trigger, "launch_writer") as launch:
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
            rc = capture_trigger.main()
        return rc, launch


class TestGitCommitAlwaysTriggersRegardlessOfDiffState(unittest.TestCase):
    def test_git_commit_classifies_as_git_diff_even_with_a_clean_working_tree(self):
        payload = {"cwd": "/repo", "tool_name": "Bash", "tool_input": {"command": "git commit -m 'x'"}}
        with mock.patch.object(capture_trigger, "_has_non_whitespace_diff", return_value=False):
            self.assertEqual(capture_trigger.classify(payload), "git-diff")

    def test_git_commit_launches_the_writer(self):
        payload = {"cwd": "/repo", "tool_name": "Bash", "tool_input": {"command": "git commit -am 'msg'"}}
        with mock.patch.object(capture_trigger, "_has_non_whitespace_diff", return_value=False):
            rc, launch = run_main(payload)
        self.assertEqual(rc, 0)
        launch.assert_called_once_with("/repo", "git-diff")


class TestNonCommitGitCommandWithNoDiffDoesNotTrigger(unittest.TestCase):
    def test_git_status_with_no_non_whitespace_diff_produces_no_trigger(self):
        payload = {"cwd": "/repo", "tool_name": "Bash", "tool_input": {"command": "git status"}}
        with mock.patch.object(capture_trigger, "_has_non_whitespace_diff", return_value=False):
            self.assertIsNone(capture_trigger.classify(payload))
            rc, launch = run_main(payload)
        self.assertEqual(rc, 0)
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
