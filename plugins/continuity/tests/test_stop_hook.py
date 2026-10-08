"""tests/test_stop_hook.py — CONTINUI-66: the end-of-turn nudge and the marker
capture-trigger.py keeps for it."""

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


stop = load_hook("stop")
capture_trigger = load_hook("capture-trigger")


def run_stop(payload, env=None):
    with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), mock.patch.dict(os.environ, env or {}, clear=False):
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            code = stop.main()
    return code, out.getvalue()


class StoreCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        self.store = os.path.join(self.root, ".continuity")
        self.staged = os.path.join(self.store, ".staged")
        self.marker = os.path.join(self.store, ".turn-edited")
        os.makedirs(self.staged)

    def tearDown(self):
        self._tmp.cleanup()

    def edit_turn(self):
        open(self.marker, "a").close()


class TestStopGate(StoreCase):
    def test_editing_turn_with_nothing_staged_blocks_once_for_claude(self):
        self.edit_turn()
        code, out = run_stop({"hook_event_name": "Stop", "cwd": self.root, "stop_hook_active": False})
        self.assertEqual(code, 0)
        result = json.loads(out)
        self.assertEqual(result["decision"], "block")
        self.assertIn(os.path.abspath(self.staged), result["reason"])
        self.assertFalse(os.path.exists(self.marker))
        # The marker is gone, so the next Stop in the same session is silent.
        self.assertEqual(run_stop({"hook_event_name": "Stop", "cwd": self.root}), (0, ""))

    def test_turn_without_edits_is_silent(self):
        self.assertEqual(run_stop({"hook_event_name": "Stop", "cwd": self.root}), (0, ""))

    def test_reentry_pass_is_silent_and_clears_the_marker(self):
        self.edit_turn()
        self.assertEqual(run_stop({"hook_event_name": "Stop", "cwd": self.root, "stop_hook_active": True}), (0, ""))
        self.assertFalse(os.path.exists(self.marker))

    def test_note_still_staged_is_silent(self):
        self.edit_turn()
        with open(os.path.join(self.staged, "learning-20261008T000000Z-1.md"), "w") as handle:
            handle.write("x\n")
        self.assertEqual(run_stop({"hook_event_name": "Stop", "cwd": self.root}), (0, ""))

    def test_project_without_a_store_is_silent(self):
        with tempfile.TemporaryDirectory() as bare:
            self.assertEqual(run_stop({"hook_event_name": "Stop", "cwd": bare}), (0, ""))


class TestStopConsolidatesStagedNotes(StoreCase):
    """A note staged without a meaningful-edit trigger (e.g. Codex's shell
    redirect) is consolidated at Stop, even when no turn marker is set."""

    def test_staged_note_without_marker_launches_writer(self):
        open(os.path.join(self.staged, "decision-20261008T000000Z-1.md"), "w").close()
        with mock.patch.object(stop, "launch_writer") as launch:
            self.assertEqual(run_stop({"hook_event_name": "Stop", "cwd": self.root}), (0, ""))
        launch.assert_called_once_with(self.root)

    def test_empty_staged_dir_launches_nothing(self):
        with mock.patch.object(stop, "launch_writer") as launch:
            run_stop({"hook_event_name": "Stop", "cwd": self.root})
        launch.assert_not_called()

    def test_writer_launch_failure_does_not_raise(self):
        open(os.path.join(self.staged, "task-20261008T000000Z-1.md"), "w").close()
        with mock.patch.object(stop.subprocess, "Popen", side_effect=OSError("no python")):
            self.assertEqual(run_stop({"hook_event_name": "Stop", "cwd": self.root}), (0, ""))

    def test_launch_uses_writer_with_stop_trigger(self):
        with mock.patch.object(stop.subprocess, "Popen") as popen:
            stop.launch_writer(self.root)
        argv = popen.call_args.args[0]
        self.assertEqual(argv[1], stop.WRITER)
        self.assertEqual(argv[2:], [self.root, "stop"])


class TestStopAcrossAgents(StoreCase):
    def test_cursor_gets_a_followup_message(self):
        self.edit_turn()
        code, out = run_stop({"hook_event_name": "stop", "status": "completed", "loop_count": 0}, {"CURSOR_PROJECT_DIR": self.root})
        self.assertEqual(set(json.loads(out)), {"followup_message"})

    def test_cursor_followup_turn_is_silent(self):
        self.edit_turn()
        self.assertEqual(run_stop({"hook_event_name": "stop", "status": "completed", "loop_count": 1}, {"CURSOR_PROJECT_DIR": self.root}), (0, ""))

    def test_cursor_aborted_turn_is_silent(self):
        self.edit_turn()
        self.assertEqual(run_stop({"hook_event_name": "stop", "status": "aborted", "loop_count": 0}, {"CURSOR_PROJECT_DIR": self.root}), (0, ""))


class TestStopFailsOpen(StoreCase):
    def test_garbage_stdin_is_silent(self):
        with mock.patch.object(sys, "stdin", io.StringIO("not json")):
            out = io.StringIO()
            with mock.patch.object(sys, "stdout", out):
                self.assertEqual(stop.main(), 0)
        self.assertEqual(out.getvalue(), "")

    def test_internal_error_is_silent(self):
        self.edit_turn()
        with mock.patch.object(stop, "decide", side_effect=RuntimeError("boom")), mock.patch("lib.common.continuity_log"):
            self.assertEqual(run_stop({"hook_event_name": "Stop", "cwd": self.root}), (0, ""))


class TestCaptureTriggerMarksTheTurn(StoreCase):
    def test_project_edit_sets_the_marker(self):
        capture_trigger.mark_turn(self.root, os.path.join(self.root, "a.py"))
        self.assertTrue(os.path.exists(self.marker))

    def test_git_trigger_without_a_file_sets_the_marker(self):
        capture_trigger.mark_turn(self.root, None)
        self.assertTrue(os.path.exists(self.marker))

    def test_staging_a_note_clears_the_marker(self):
        self.edit_turn()
        capture_trigger.mark_turn(self.root, os.path.join(self.staged, "decision-20261008T000000Z-1.md"))
        self.assertFalse(os.path.exists(self.marker))

    def test_no_store_creates_nothing(self):
        with tempfile.TemporaryDirectory() as bare:
            capture_trigger.mark_turn(bare, os.path.join(bare, "a.py"))
            self.assertEqual(os.listdir(bare), [])

    def test_main_marks_before_launching(self):
        os.mkdir(os.path.join(self.root, ".git"))
        payload = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "cwd": self.root,
                   "tool_input": {"file_path": os.path.join(self.root, "a.py"), "old_string": "a", "new_string": "b"}}
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), mock.patch.object(capture_trigger, "launch_writer"):
            capture_trigger.main()
        self.assertTrue(os.path.exists(self.marker))


if __name__ == "__main__":
    unittest.main()
