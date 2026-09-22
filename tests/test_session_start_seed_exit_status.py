"""tests/test_session_start_seed_exit_status.py — CONTINUI-46 exit-code contract.

hooks/session-start.py -> build_context() seeds `.continuity/` when it finds
none (CONTINUI-46). Every other test file for this feature checks what gets
written to disk or injected as context; this file isolates one narrower
claim that a hook contract lives and dies by: whatever seeding does or does
not manage to do, the hook process itself always exits 0 (FR-012). A
SessionStart hook that ever exits non-zero can block the session it was
only ever supposed to observe.

Four cases:
  - seeding succeeds            -> exit 0
  - the store already exists    -> exit 0, and the seed path is never taken
  - store creation fails        -> exit 0 (permission denied, and simulated
                                    disk-full via a patched atomic_write)
  - an existing store's files survive an unrelated SessionStart call
    unmodified, byte for byte and mtime for mtime
"""

import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

import lib.migrate as migrate_module
from lib.migrate import SEED_FILES

SESSION_START_HOOK = os.path.join(REPO_ROOT, "hooks", "session-start.py")

PERMISSIONS_ENFORCED = os.name != "nt" and getattr(os, "geteuid", lambda: 1)() != 0

_SPEC = importlib.util.spec_from_file_location("session_start_exit_status", SESSION_START_HOOK)
session_start = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(session_start)


def run_session_start(project_root):
    return subprocess.run(
        [sys.executable, SESSION_START_HOOK],
        input=json.dumps({"session_id": "s", "cwd": project_root}),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )


def run_hook_in_process(cwd):
    """Drive main() over a stdin payload; return (exit_code, parsed_output)."""
    stdout = io.StringIO()
    stdin = io.StringIO(json.dumps({"session_id": "s", "cwd": cwd}))
    orig_stdin, orig_stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = stdin, stdout
    try:
        code = session_start.main()
    finally:
        sys.stdin, sys.stdout = orig_stdin, orig_stdout
    return code, json.loads(stdout.getvalue())


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    return path


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def snapshot(store):
    """(content, mtime_ns) per file, so "untouched" means untouched."""
    result = {}
    for name in os.listdir(store):
        path = os.path.join(store, name)
        if os.path.isfile(path):
            result[name] = (read(path), os.stat(path).st_mtime_ns)
    return result


class TestExitsZeroWhenSeedingSucceeds(unittest.TestCase):
    def test_process_exit_code_is_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_session_start(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(os.path.isdir(os.path.join(tmp, ".continuity")))

    def test_in_process_main_returns_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, _output = run_hook_in_process(tmp)

            self.assertEqual(code, 0)


class TestExitsZeroWhenStoreAlreadyExists(unittest.TestCase):
    def test_process_exit_code_is_zero_over_a_live_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            write(
                os.path.join(store, "metadata.json"),
                json.dumps(
                    {"schema_version": migrate_module.CURRENT_SCHEMA_VERSION, "created_at": "2026-01-01T00:00:00Z"}
                ),
            )

            result = run_session_start(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)

    def test_seed_store_is_never_invoked_for_an_existing_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            write(
                os.path.join(store, "metadata.json"),
                json.dumps(
                    {"schema_version": migrate_module.CURRENT_SCHEMA_VERSION, "created_at": "2026-01-01T00:00:00Z"}
                ),
            )

            with patch.object(session_start, "seed_store") as seed_store_mock:
                code, _output = run_hook_in_process(tmp)

            self.assertEqual(code, 0)
            seed_store_mock.assert_not_called()


class TestExitsZeroWhenStoreCreationFails(unittest.TestCase):
    def test_simulated_disk_full_during_seeding_still_exits_zero(self):
        """A write failure mid-seed (e.g. ENOSPC) is FR-012's fail-open path."""
        with tempfile.TemporaryDirectory() as tmp:

            def raise_disk_full(_target, _content):
                raise OSError(28, "No space left on device")  # ENOSPC

            with patch.object(migrate_module, "atomic_write", raise_disk_full):
                code, output = run_hook_in_process(tmp)

            self.assertEqual(code, 0)
            self.assertNotIn(
                "additionalContext", output.get("hookSpecificOutput", {})
            )

    @unittest.skipUnless(PERMISSIONS_ENFORCED, "chmod is not enforced here")
    def test_permission_denied_creating_the_store_still_exits_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            original = stat.S_IMODE(os.stat(project).st_mode)
            os.chmod(project, 0o500)  # r-x: cannot create .continuity/ under it
            try:
                result = run_session_start(project)
            finally:
                os.chmod(project, original)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            output = json.loads(result.stdout)
            self.assertNotIn(
                "additionalContext", output.get("hookSpecificOutput", {})
            )


class TestExistingStoreNeverModifiedBySubsequentCalls(unittest.TestCase):
    def test_files_are_byte_for_byte_and_mtime_identical_after_a_second_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_session_start(tmp)  # first call: seeds the store
            store = os.path.join(tmp, ".continuity")
            before = snapshot(store)
            self.assertTrue(before, "store must have been seeded before this assertion")

            time.sleep(0.01)  # make an accidental rewrite's mtime detectable
            run_session_start(tmp)  # second call: must be a pure no-op on disk
            after = snapshot(store)

            self.assertEqual(before, after)

    def test_hand_edited_seed_files_survive_repeated_calls_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            write(
                os.path.join(store, "metadata.json"),
                json.dumps(
                    {"schema_version": migrate_module.CURRENT_SCHEMA_VERSION, "created_at": "2026-01-01T00:00:00Z"}
                ),
            )
            # state.md must carry a parseable `updated_at` fence — its reader
            # (select_context._read_state) logs "corrupted" to errors.log for
            # any other content, which would make this fixture exercise that
            # unrelated read path instead of the seeding no-op this test is
            # actually about.
            write(
                os.path.join(store, "state.md"),
                "# Project state\n\n```\nupdated_at: 2026-01-01T00:00:00Z\n```\n\nhand-edited\n",
            )
            for name in SEED_FILES:
                if name == "state.md":
                    continue
                write(os.path.join(store, name), "# hand-edited: " + name + "\n")
            before = snapshot(store)

            time.sleep(0.01)
            run_session_start(tmp)
            run_session_start(tmp)
            after = snapshot(store)

            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
