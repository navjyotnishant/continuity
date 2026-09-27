"""tests/test_write_path_detaches_background.py — CONTINUI-12 (US2: Never
notice Continuity is running).

FR-010 / research.md R4: the writer `lib/write_memory.py` must run as an
orphaned background process, not a child the interactive turn (or its
hook) has to wait on or that dies when the hook's process group is torn
down. Proven two ways: the launching hook returns immediately even against
a writer that sleeps far longer than any turn would wait, and — on POSIX —
the spawned writer lands in its own session rather than the hook's.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

CAPTURE_TRIGGER_SRC = os.path.join(REPO_ROOT, "hooks", "capture-trigger.py")
SESSION_END_SRC = os.path.join(REPO_ROOT, "hooks", "session-end.py")

SLOW_WRITER_STUB = "import time\ntime.sleep(2)\n"
RETURN_WITHIN_SECONDS = 0.5


def build_fake_plugin(root, hook_src, hook_basename, writer_body):
    hooks_dir = os.path.join(root, "hooks")
    lib_dir = os.path.join(root, "lib")
    os.makedirs(hooks_dir)
    os.makedirs(lib_dir)
    shutil.copy2(hook_src, os.path.join(hooks_dir, hook_basename))
    with open(os.path.join(lib_dir, "write_memory.py"), "w", encoding="utf-8") as handle:
        handle.write(writer_body)
    return os.path.join(hooks_dir, hook_basename)


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


class TestWritePathDetachesFromCaptureTrigger(unittest.TestCase):
    def test_writer_launch_does_not_block_the_hook_process(self):
        with tempfile.TemporaryDirectory() as plugin_root, tempfile.TemporaryDirectory() as project:
            hook = build_fake_plugin(
                plugin_root, CAPTURE_TRIGGER_SRC, "capture-trigger.py", SLOW_WRITER_STUB
            )
            result, elapsed = run_hook(
                hook,
                {
                    "cwd": project,
                    "tool_name": "Write",
                    "tool_input": {"content": "print(1)\n"},
                },
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(elapsed, RETURN_WITHIN_SECONDS)


class TestWritePathDetachesFromSessionEnd(unittest.TestCase):
    def test_writer_launch_does_not_block_the_hook_process(self):
        with tempfile.TemporaryDirectory() as plugin_root, tempfile.TemporaryDirectory() as project:
            hook = build_fake_plugin(
                plugin_root, SESSION_END_SRC, "session-end.py", SLOW_WRITER_STUB
            )
            result, elapsed = run_hook(hook, {"cwd": project})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(elapsed, RETURN_WITHIN_SECONDS)


@unittest.skipIf(os.name == "nt", "session reparenting is POSIX-specific")
class TestWriterProcessIsReparentedOnPosix(unittest.TestCase):
    """A subprocess spawned with start_new_session=True gets its own session,
    so it survives (and cannot be waited on by) the hook that launched it —
    the actual mechanism behind "detaches as a background process".
    """

    def test_spawned_writer_gets_a_different_session_than_the_hook(self):
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "capture_trigger_detach_check", CAPTURE_TRIGGER_SRC
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as project:
            sid_file = os.path.join(project, "sid.txt")
            writer = os.path.join(project, "record_sid.py")
            with open(writer, "w", encoding="utf-8") as handle:
                handle.write(
                    "import os\n"
                    "with open({sid_file!r}, 'w') as f:\n"
                    "    f.write(str(os.getsid(0)))\n".format(sid_file=sid_file)
                )

            parent_sid = os.getsid(0)
            module.launch_writer(project, "file-change", writer=writer)

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline and not os.path.exists(sid_file):
                time.sleep(0.05)
            self.assertTrue(os.path.exists(sid_file), "background writer never ran")
            child_sid = int(open(sid_file, encoding="utf-8").read())
            self.assertNotEqual(child_sid, parent_sid)


if __name__ == "__main__":
    unittest.main()
