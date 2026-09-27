"""tests/test_agent_hooks.py — the hook scripts driven by Codex and Cursor payloads."""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)


def load_hook(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(REPO_ROOT, "hooks", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture_trigger = load_hook("capture-trigger")
session_end = load_hook("session-end")
session_start = load_hook("session-start")


def run_main(module, payload, env=None):
    stdin = io.StringIO(json.dumps(payload))
    with mock.patch.object(sys, "stdin", stdin), mock.patch.dict(os.environ, env or {}, clear=False):
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            code = module.main()
    return code, out.getvalue()


class TestCaptureTriggerAcrossAgents(unittest.TestCase):
    def test_codex_patch_across_two_repos_launches_one_writer_each(self):
        # Review Focus 2
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            os.mkdir(os.path.join(a, ".git"))
            os.mkdir(os.path.join(b, ".git"))
            patch = "*** Update File: %s/x.py\n-1\n+2\n*** Update File: %s/y.py\n-1\n+2\n*** Update File: %s/z.py\n-1\n+2\n" % (a, b, b)
            payload = {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "cwd": a, "tool_input": {"command": patch}}
            with mock.patch.object(capture_trigger, "launch_writer") as launch:
                self.assertEqual(run_main(capture_trigger, payload)[0], 0)
            self.assertEqual(sorted(c.args[0] for c in launch.call_args_list), sorted([a, b]))

    def test_cursor_after_file_edit_launches_writer_in_project(self):
        with tempfile.TemporaryDirectory() as root:
            payload = {"hook_event_name": "afterFileEdit", "file_path": os.path.join(root, "a.py"), "edits": [{"old_string": "a", "new_string": "b"}]}
            with mock.patch.object(capture_trigger, "launch_writer") as launch:
                run_main(capture_trigger, payload, {"CURSOR_PROJECT_DIR": root})
            launch.assert_called_once_with(root, "file-change")

    def test_cursor_whitespace_only_edit_launches_nothing(self):
        payload = {"hook_event_name": "afterFileEdit", "file_path": "/r/a.py", "edits": [{"old_string": "a b", "new_string": "a  b"}]}
        with mock.patch.object(capture_trigger, "launch_writer") as launch:
            run_main(capture_trigger, payload, {"CURSOR_PROJECT_DIR": "/r"})
        launch.assert_not_called()

    def test_unmapped_cursor_event_is_a_silent_no_op(self):
        # Review Focus 5
        with mock.patch.object(capture_trigger, "launch_writer") as launch, mock.patch.object(capture_trigger, "_log") as log:
            code, out = run_main(capture_trigger, {"hook_event_name": "stop"}, {"CURSOR_PROJECT_DIR": "/r"})
        self.assertEqual((code, out), (0, ""))
        launch.assert_not_called()
        log.assert_not_called()


class TestSessionEndAcrossAgents(unittest.TestCase):
    def test_cursor_session_end_flushes_the_project(self):
        with mock.patch.object(session_end, "launch_writer") as launch:
            run_main(session_end, {"hook_event_name": "sessionEnd"}, {"CURSOR_PROJECT_DIR": "/work/repo"})
        launch.assert_called_once_with("/work/repo")


class TestSessionStartAcrossAgents(unittest.TestCase):
    def test_cursor_gets_additional_context_for_its_project(self):
        with tempfile.TemporaryDirectory() as root:
            code, out = run_main(session_start, {"hook_event_name": "sessionStart"}, {"CURSOR_PROJECT_DIR": root})
            self.assertEqual(code, 0)
            context = json.loads(out)["additional_context"]
            self.assertIn(os.path.join(root, ".continuity", ".staged"), context)

    def test_codex_start_output_is_the_claude_shape(self):
        with tempfile.TemporaryDirectory() as root:
            _, out = run_main(session_start, {"hook_event_name": "SessionStart", "cwd": root})
            self.assertIn("additionalContext", json.loads(out)["hookSpecificOutput"])

    def test_claude_output_unchanged_with_cursor_env_present(self):
        # Review Focus 1
        with tempfile.TemporaryDirectory() as root:
            _, plain = run_main(session_start, {"hook_event_name": "SessionStart", "cwd": root})
            _, with_env = run_main(session_start, {"hook_event_name": "SessionStart", "cwd": root}, {"CURSOR_VERSION": "2.0", "CURSOR_PROJECT_DIR": "/elsewhere"})
            self.assertEqual(plain, with_env)


if __name__ == "__main__":
    unittest.main()
