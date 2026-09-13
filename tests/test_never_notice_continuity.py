"""tests/test_never_notice_continuity.py — CONTINUI-12 (US2: Never notice
Continuity is running).

spec.md US2 scenario 1 + contracts/hook-io-contract.md's PostToolUse rule:
the tools that can be a meaningful-change signal (Edit, Write, MultiEdit,
Bash) launch the detached writer; Read never does, because it changes
nothing; and a whitespace-only edit is a documented no-op regardless of
which edit tool produced it. None of this may cost the interactive turn a
wait on the writer.
"""

import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

CAPTURE_TRIGGER_SRC = os.path.join(REPO_ROOT, "hooks", "capture-trigger.py")

_SPEC = importlib.util.spec_from_file_location(
    "capture_trigger_us2", CAPTURE_TRIGGER_SRC
)
capture_trigger = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(capture_trigger)

# Matches test_detach.py's margin: generous enough to absorb interpreter
# startup, far too tight to have waited out a writer that sleeps for 2s.
RETURN_WITHIN_SECONDS = 0.1
SLOW_WRITER_STUB = "import time\ntime.sleep(2)\n"


def build_fake_plugin(root, writer_body):
    hooks_dir = os.path.join(root, "hooks")
    lib_dir = os.path.join(root, "lib")
    os.makedirs(hooks_dir)
    os.makedirs(lib_dir)
    shutil.copy2(CAPTURE_TRIGGER_SRC, os.path.join(hooks_dir, "capture-trigger.py"))
    with open(os.path.join(lib_dir, "write_memory.py"), "w", encoding="utf-8") as handle:
        handle.write(writer_body)
    return os.path.join(hooks_dir, "capture-trigger.py")


def run_hook(hook_path, payload, timeout=30):
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, hook_path],
        input=json.dumps(payload),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    return result, time.monotonic() - started


def run_main(payload):
    """Feed payload to capture_trigger.main() via stdin, return (rc, launch mock)."""
    with mock.patch.object(capture_trigger, "launch_writer") as launch:
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
            rc = capture_trigger.main()
        return rc, launch


class TestMemoryWriteIsAsynchronous(unittest.TestCase):
    def test_hook_returns_long_before_a_slow_writer_would_finish(self):
        with tempfile.TemporaryDirectory() as plugin_root, tempfile.TemporaryDirectory() as project:
            hook = build_fake_plugin(plugin_root, SLOW_WRITER_STUB)
            result, elapsed = run_hook(
                hook,
                {
                    "cwd": project,
                    "tool_name": "Edit",
                    "tool_input": {"old_string": "x = 1", "new_string": "x = 2"},
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(elapsed, RETURN_WITHIN_SECONDS)


class TestEditToolTriggersWrite(unittest.TestCase):
    def test_edit_with_real_change_launches_the_writer(self):
        payload = {
            "cwd": "/tmp/project",
            "tool_name": "Edit",
            "tool_input": {"old_string": "foo", "new_string": "bar"},
        }
        self.assertEqual(capture_trigger.classify(payload), "file-change")
        rc, launch = run_main(payload)
        self.assertEqual(rc, 0)
        launch.assert_called_once_with("/tmp/project", "file-change")


class TestWriteToolTriggersWrite(unittest.TestCase):
    def test_write_with_real_content_launches_the_writer(self):
        payload = {
            "cwd": "/tmp/project",
            "tool_name": "Write",
            "tool_input": {"content": "print('hello')\n"},
        }
        self.assertEqual(capture_trigger.classify(payload), "file-change")
        rc, launch = run_main(payload)
        self.assertEqual(rc, 0)
        launch.assert_called_once_with("/tmp/project", "file-change")


class TestMultiEditToolTriggersWrite(unittest.TestCase):
    def test_multiedit_with_real_change_launches_the_writer(self):
        payload = {
            "cwd": "/tmp/project",
            "tool_name": "MultiEdit",
            "tool_input": {
                "edits": [
                    {"old_string": "foo", "new_string": "bar"},
                    {"old_string": "  a", "new_string": "a"},
                ]
            },
        }
        self.assertEqual(capture_trigger.classify(payload), "file-change")
        rc, launch = run_main(payload)
        self.assertEqual(rc, 0)
        launch.assert_called_once_with("/tmp/project", "file-change")


class TestBashToolTriggersWrite(unittest.TestCase):
    def test_bash_git_command_with_non_whitespace_diff_launches_the_writer(self):
        payload = {"cwd": "/repo", "tool_name": "Bash", "tool_input": {"command": "git add -A"}}
        with mock.patch.object(capture_trigger, "_has_non_whitespace_diff", return_value=True):
            self.assertEqual(capture_trigger.classify(payload), "git-diff")
            with mock.patch.object(capture_trigger, "launch_writer") as launch:
                with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))):
                    rc = capture_trigger.main()
                self.assertEqual(rc, 0)
                launch.assert_called_once_with("/repo", "git-diff")


class TestReadToolDoesNotTriggerWrite(unittest.TestCase):
    def test_read_tool_use_produces_no_trigger_and_spawns_nothing(self):
        payload = {
            "cwd": "/tmp/project",
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/project/a.py"},
        }
        self.assertIsNone(capture_trigger.classify(payload))
        rc, launch = run_main(payload)
        self.assertEqual(rc, 0)
        launch.assert_not_called()


class TestWhitespaceOnlyEditsDoNotTriggerWrite(unittest.TestCase):
    def test_edit_whitespace_only_produces_no_trigger(self):
        payload = {
            "cwd": "/tmp/project",
            "tool_name": "Edit",
            "tool_input": {"old_string": "foo\n  bar", "new_string": "foo\nbar"},
        }
        self.assertIsNone(capture_trigger.classify(payload))
        rc, launch = run_main(payload)
        self.assertEqual(rc, 0)
        launch.assert_not_called()

    def test_write_whitespace_only_produces_no_trigger(self):
        payload = {"cwd": "/tmp/project", "tool_name": "Write", "tool_input": {"content": "  \n\t\n"}}
        self.assertIsNone(capture_trigger.classify(payload))
        rc, launch = run_main(payload)
        self.assertEqual(rc, 0)
        launch.assert_not_called()

    def test_multiedit_all_whitespace_only_edits_produce_no_trigger(self):
        payload = {
            "cwd": "/tmp/project",
            "tool_name": "MultiEdit",
            "tool_input": {
                "edits": [
                    {"old_string": "foo\n  bar", "new_string": "foo\nbar"},
                    {"old_string": "a  b", "new_string": "a b"},
                ]
            },
        }
        self.assertIsNone(capture_trigger.classify(payload))
        rc, launch = run_main(payload)
        self.assertEqual(rc, 0)
        launch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
