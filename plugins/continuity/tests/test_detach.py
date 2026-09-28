"""tests/test_detach.py — the never-wait contract for both hooks (T020).

`hooks/capture-trigger.py` and `hooks/session-end.py` must return to Claude
Code immediately after launching `lib/write_memory.py`, never awaiting it
(FR-010). Proven here by swapping in a `write_memory.py` stub that sleeps for
2 seconds and asserting the hook itself returns in a small fraction of that
— a margin wide enough to absorb interpreter startup but far too tight to
have waited for the stub.

Also covers: the writer subprocess is detached with the platform-specific
`start_new_session=True` (POSIX) / `CREATE_NEW_PROCESS_GROUP |
DETACHED_PROCESS` (Windows) kwargs (plan.md's Constraints, research.md R4),
and that the writer itself runs one consolidation pass and exits rather than
looping or listening for further input.
"""

import importlib.util
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
SESSION_END_SRC = os.path.join(REPO_ROOT, "hooks", "session-end.py")
WRITE_MEMORY_SRC = os.path.join(REPO_ROOT, "lib", "write_memory.py")

SLOW_WRITER_STUB = (
    "import time\n"
    "time.sleep(2)\n"
)

# The margin below the stub's 2-second sleep that proves the hook did not
# wait: generous enough to absorb interpreter startup, tight enough that
# only "detached and returned immediately" can pass it. Matches the <100ms
# timing margin named for this case (existing coverage measures ~41ms for
# the real, non-stub writer path).
RETURN_WITHIN_SECONDS = 0.1


def load_module(path, name):
    """Import a hyphenated hook script by path (it can't be `import`ed)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_fake_plugin(root, hook_src, hook_basename, writer_body):
    """Lay out `<root>/hooks/<hook_basename>` + `<root>/lib/write_memory.py`.

    Both real hooks resolve their writer path relative to their own file
    location (`PLUGIN_ROOT`), so copying the real hook script into a fixture
    tree alongside a stub writer makes it run against the stub without
    touching the hook's own source.
    """
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


class TestCaptureTriggerNeverWaits(unittest.TestCase):
    def test_returns_well_before_the_stub_writer_finishes_sleeping(self):
        with tempfile.TemporaryDirectory() as plugin_root, tempfile.TemporaryDirectory() as project:
            hook = build_fake_plugin(
                plugin_root, CAPTURE_TRIGGER_SRC, "capture-trigger.py", SLOW_WRITER_STUB
            )
            result, elapsed = run_hook(
                hook,
                {
                    "session_id": "s",
                    "cwd": project,
                    "tool_name": "Edit",
                    "tool_input": {
                        "file_path": os.path.join(project, "a.py"),
                        "old_string": "x = 1",
                        "new_string": "x = 2",
                    },
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(elapsed, RETURN_WITHIN_SECONDS)


class TestSessionEndNeverWaits(unittest.TestCase):
    """hooks/session-end.py per contracts/hook-io-contract.md -> SessionEnd:
    reads stdin, unconditionally launches the writer detached, exits with no
    output. Not yet implemented as of this writing (T022) — this test is
    written against the contract and is expected to fail until it lands.
    """

    def test_returns_well_before_the_stub_writer_finishes_sleeping(self):
        with tempfile.TemporaryDirectory() as plugin_root, tempfile.TemporaryDirectory() as project:
            hook = build_fake_plugin(
                plugin_root, SESSION_END_SRC, "session-end.py", SLOW_WRITER_STUB
            )
            result, elapsed = run_hook(hook, {"session_id": "s", "cwd": project})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(elapsed, RETURN_WITHIN_SECONDS)

    def test_launches_the_writer_unconditionally_with_no_output(self):
        # Unlike PostToolUse, SessionEnd has no classification step: every
        # invocation must fire the writer, and the hook itself prints
        # nothing (contracts/hook-io-contract.md -> SessionEnd).
        marker_writer = (
            "import sys\n"
            "with open(sys.argv[1] + '/fired.marker', 'w') as handle:\n"
            "    handle.write(sys.argv[2] if len(sys.argv) > 2 else '')\n"
        )
        with tempfile.TemporaryDirectory() as plugin_root, tempfile.TemporaryDirectory() as project:
            hook = build_fake_plugin(
                plugin_root, SESSION_END_SRC, "session-end.py", marker_writer
            )
            result, _ = run_hook(hook, {"session_id": "s", "cwd": project})

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")

            deadline = time.monotonic() + 5.0
            marker = os.path.join(project, "fired.marker")
            while time.monotonic() < deadline and not os.path.exists(marker):
                time.sleep(0.05)
            self.assertTrue(os.path.exists(marker), "writer was never launched")


class TestWriterRunsOnePassAndExits(unittest.TestCase):
    """lib/write_memory.py is a one-shot CLI, not a loop or a listener: it
    must finish and exit on its own with no further input, every time it is
    invoked — which is what lets a hook fire-and-forget it (FR-010).
    """

    def stage(self, project_root, suffix):
        path = os.path.join(
            project_root, ".continuity", ".staged", "decision-{}.md".format(suffix)
        )
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("# Note\n\nBody.\n")
        return path

    def test_process_exits_on_its_own_without_further_input(self):
        with tempfile.TemporaryDirectory() as project:
            self.stage(project, "20260912T140501Z-1")

            process = subprocess.Popen(
                [sys.executable, WRITE_MEMORY_SRC, project, "session-end"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            # A listener that never reads stdin (because it is waiting on a
            # socket, a queue, or another turn) would still be alive here;
            # a one-shot script has already finished.
            returncode = process.wait(timeout=10)

            self.assertEqual(returncode, 0)
            self.assertIsNotNone(process.poll(), "process must not still be running")

    def test_two_consecutive_invocations_each_do_exactly_one_pass(self):
        with tempfile.TemporaryDirectory() as project:
            self.stage(project, "20260912T140501Z-1")
            first = subprocess.run(
                [sys.executable, WRITE_MEMORY_SRC, project, "file-change"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertIn("Checkpoint written to", first.stdout)

            # Nothing staged the second time: a looping/listening process
            # would still be "running" from the first call and this second,
            # independent process launch would hang waiting on it instead.
            second = subprocess.run(
                [sys.executable, WRITE_MEMORY_SRC, project, "file-change"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("Nothing new to checkpoint", second.stdout)


class TestDetachKwargs(unittest.TestCase):
    """detach_kwargs() from hooks/capture-trigger.py (research.md R4)."""

    def setUp(self):
        self.module = load_module(CAPTURE_TRIGGER_SRC, "capture_trigger_under_test")

    def test_posix_uses_start_new_session(self):
        with mock.patch.object(self.module.os, "name", "posix"):
            self.assertEqual(self.module.detach_kwargs(), {"start_new_session": True})

    def test_windows_uses_detached_process_creation_flags(self):
        with mock.patch.object(self.module.os, "name", "nt"), mock.patch.object(
            self.module.subprocess,
            "CREATE_NEW_PROCESS_GROUP",
            0x00000200,
            create=True,
        ), mock.patch.object(
            self.module.subprocess, "DETACHED_PROCESS", 0x00000008, create=True
        ):
            kwargs = self.module.detach_kwargs()
            self.assertIn("creationflags", kwargs)
            self.assertEqual(kwargs["creationflags"], 0x00000200 | 0x00000008)
            # No console inheritance: DETACHED_PROCESS must be set, not just
            # a new process group (a new group alone still inherits the
            # console on Windows).
            self.assertTrue(kwargs["creationflags"] & 0x00000008)


@unittest.skipIf(os.name == "nt", "session reparenting is POSIX-specific")
class TestWriterIsReparentedOnPosix(unittest.TestCase):
    def test_spawned_writer_gets_its_own_session_not_the_hooks(self):
        module = load_module(CAPTURE_TRIGGER_SRC, "capture_trigger_under_test_posix")
        with tempfile.TemporaryDirectory() as project:
            sid_file = os.path.join(project, "sid.txt")
            writer = os.path.join(project, "record_sid.py")
            # launch_writer calls `[python, writer, cwd, trigger_kind]` —
            # only two fixed positional args — so the sid_file path is
            # baked into the script body rather than read from argv.
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
            self.assertTrue(os.path.exists(sid_file), "reparented writer never ran")
            child_sid = int(open(sid_file, encoding="utf-8").read())
            self.assertNotEqual(
                child_sid, parent_sid, "writer must not share the hook's session"
            )


if __name__ == "__main__":
    unittest.main()
