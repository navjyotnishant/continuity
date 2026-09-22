"""tests/test_session_start_seed_contents_and_fail_open.py — CONTINUI-46.

Covers four claims about hooks/session-start.py's seeding path that the
other CONTINUI-46 test files do not already pin down together:

  1. the session proceeds normally when store creation fails (FR-012)
  2. no additionalContext is injected when store creation fails
  3. the files a successful seed writes have readable, well-formed content
  4. a successful seed creates exactly the four durable files plus
     metadata.json — nothing else
"""

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

import lib.migrate as migrate_module
from lib.migrate import CURRENT_SCHEMA_VERSION, SEED_FILES

SESSION_START_HOOK = os.path.join(REPO_ROOT, "hooks", "session-start.py")

# chmod is advisory for root, and native Windows ignores the POSIX mode bits
# outright, so the permission-denied case proves nothing there.
PERMISSIONS_ENFORCED = os.name != "nt" and getattr(os, "geteuid", lambda: 1)() != 0


def run_session_start(project_root):
    return subprocess.run(
        [sys.executable, SESSION_START_HOOK],
        input=json.dumps({"session_id": "s", "cwd": project_root}),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class TestSessionProceedsWhenStoreCreationFails(unittest.TestCase):
    """FR-012: a store that cannot be created must not block the session."""

    def test_simulated_write_failure_still_exits_zero_with_no_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:

            def raise_disk_full(_target, _content):
                raise OSError(28, "No space left on device")

            with patch.object(migrate_module, "atomic_write", raise_disk_full):
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

    @unittest.skipUnless(PERMISSIONS_ENFORCED, "chmod is not enforced here")
    def test_unwritable_project_root_still_exits_zero_with_no_stderr(self):
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
            self.assertFalse(os.path.exists(os.path.join(project, ".continuity")))


class TestNoAdditionalContextWhenStoreCreationFails(unittest.TestCase):
    """A store that failed to seed still has no prior session to report."""

    def test_simulated_write_failure_injects_no_additional_context(self):
        with tempfile.TemporaryDirectory() as tmp:

            def raise_disk_full(_target, _content):
                raise OSError(28, "No space left on device")

            with patch.object(migrate_module, "atomic_write", raise_disk_full):
                result = subprocess.run(
                    [sys.executable, SESSION_START_HOOK],
                    input=json.dumps({"session_id": "s", "cwd": tmp}),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30,
                )

            output = json.loads(result.stdout)
            self.assertNotIn(
                "additionalContext", output.get("hookSpecificOutput", {})
            )

    @unittest.skipUnless(PERMISSIONS_ENFORCED, "chmod is not enforced here")
    def test_unwritable_project_root_injects_no_additional_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            original = stat.S_IMODE(os.stat(project).st_mode)
            os.chmod(project, 0o500)
            try:
                result = run_session_start(project)
            finally:
                os.chmod(project, original)

            output = json.loads(result.stdout)
            self.assertNotIn(
                "additionalContext", output.get("hookSpecificOutput", {})
            )


class TestSeededFilesHaveReadableContent(unittest.TestCase):
    """A seeded file must be well-formed input, not just present."""

    def test_metadata_json_parses_with_the_expected_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_session_start(tmp)

            metadata = json.loads(read(os.path.join(tmp, ".continuity", "metadata.json")))
            self.assertEqual(metadata["schema_version"], CURRENT_SCHEMA_VERSION)
            self.assertTrue(metadata["created_at"])

    def test_each_durable_file_is_non_empty_utf8_text_with_its_template_header(self):
        expected_header = {
            "state.md": "# Project state",
            "decisions.md": "# Decisions",
            "tasks.md": "# Tasks",
            "learnings.md": "# Learnings",
        }
        with tempfile.TemporaryDirectory() as tmp:
            run_session_start(tmp)

            store = os.path.join(tmp, ".continuity")
            for name in SEED_FILES:
                content = read(os.path.join(store, name))
                self.assertTrue(content.strip(), name + " was seeded empty")
                self.assertTrue(
                    content.startswith(expected_header[name]),
                    name + " does not start with its template header: " + content[:40],
                )

    def test_state_md_has_no_unsubstituted_template_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_session_start(tmp)

            state = read(os.path.join(tmp, ".continuity", "state.md"))
            self.assertNotIn("{updated_at}", state)
            self.assertRegex(
                state, r"updated_at: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
            )


class TestNoExtraFilesOrDirectoriesAreCreated(unittest.TestCase):
    """A fresh seed is exactly the four durable files plus metadata.json."""

    def test_store_contains_only_the_five_expected_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_session_start(tmp)

            store = os.path.join(tmp, ".continuity")
            expected = sorted(SEED_FILES + ("metadata.json",))
            self.assertEqual(sorted(os.listdir(store)), expected)

    def test_no_subdirectories_are_created_under_the_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_session_start(tmp)

            store = os.path.join(tmp, ".continuity")
            for entry in os.listdir(store):
                self.assertTrue(
                    os.path.isfile(os.path.join(store, entry)),
                    entry + " should be a file, not a directory",
                )

    def test_nothing_is_created_outside_the_continuity_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_session_start(tmp)

            self.assertEqual(os.listdir(tmp), [".continuity"])


if __name__ == "__main__":
    unittest.main()
