"""tests/test_session_start_no_history.py — SessionStart with no prior store.

contracts/hook-io-contract.md -> SessionStart, FR-007/FR-012: a project that
has never run Continuity has no `.continuity/` directory yet. The hook must
inject no context, must log nothing, and must never surface an error to the
session — it just proceeds normally.

CONTINUI-46 adds the other half: that first session also *seeds* the store
from `templates/*.tmpl`, so a freshly installed plugin has a `.continuity/`
immediately rather than whenever a checkpoint first happens to fire. Seeding
is still silent — it changes what is on disk afterwards, never what the hook
emits — and a store it cannot create is not an error either.
"""

import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.migrate import CURRENT_SCHEMA_VERSION, SEED_FILES

SESSION_START_HOOK = os.path.join(REPO_ROOT, "hooks", "session-start.py")

# chmod is advisory for root, and native Windows ignores the POSIX mode bits
# outright, so the unwritable-root case proves nothing there.
PERMISSIONS_ENFORCED = os.name != "nt" and getattr(os, "geteuid", lambda: 1)() != 0

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


class TestNoPriorHistorySeedsTheStore(unittest.TestCase):
    """CONTINUI-46: the first session after install creates the store."""

    def test_hook_creates_the_continuity_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)

            self.assertTrue(os.path.isdir(os.path.join(tmp, ".continuity")))

    def test_metadata_json_is_stamped_at_this_plugins_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)

            with open(
                os.path.join(tmp, ".continuity", "metadata.json"), encoding="utf-8"
            ) as handle:
                metadata = json.load(handle)
            self.assertEqual(metadata["schema_version"], CURRENT_SCHEMA_VERSION)
            self.assertTrue(metadata["created_at"])

    def test_every_durable_file_is_seeded_from_its_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)

            for name in SEED_FILES:
                path = os.path.join(tmp, ".continuity", name)
                self.assertTrue(os.path.isfile(path), name + " was not seeded")
                self.assertTrue(read(path).strip(), name + " was seeded empty")

    def test_seeded_state_has_a_real_timestamp_not_the_placeholder(self):
        """An unsubstituted `{updated_at}` makes select_context drop state.md."""
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)

            state = read(os.path.join(tmp, ".continuity", "state.md"))
            self.assertNotIn("{updated_at}", state)
            self.assertRegex(state, r"updated_at: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

    def test_seeding_is_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)

            self.assertFalse(
                os.path.exists(os.path.join(tmp, ".continuity", "errors.log"))
            )

    def test_a_seeded_store_still_injects_nothing_on_the_next_session(self):
        """A store with no recorded history has nothing to report, seeded or not."""
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)
            output = run_hook_in_process(tmp)

            self.assertNotIn(
                "additionalContext", output.get("hookSpecificOutput", {})
            )

    def test_an_existing_store_is_left_exactly_as_it_was(self):
        """Seeding fires only for an absent store — never over a live one."""
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            edited = "# Project state\n\n```\nupdated_at: 2026-01-01T00:00:00Z\n```\n"
            with open(os.path.join(store, "state.md"), "w", encoding="utf-8") as handle:
                handle.write(edited)

            run_hook_in_process(tmp)

            self.assertEqual(read(os.path.join(store, "state.md")), edited)
            self.assertEqual(sorted(os.listdir(store)), ["state.md"])

    @unittest.skipUnless(PERMISSIONS_ENFORCED, "chmod is not enforced here")
    def test_a_store_that_cannot_be_created_is_not_an_error(self):
        """FR-012: an unwritable project root fails open, exactly as before."""
        with tempfile.TemporaryDirectory() as tmp:
            project = os.path.join(tmp, "project")
            os.makedirs(project)
            original = stat.S_IMODE(os.stat(project).st_mode)
            os.chmod(project, 0o500)
            try:
                result = subprocess.run(
                    [sys.executable, SESSION_START_HOOK],
                    input=json.dumps({"session_id": "s", "cwd": project}),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30,
                )
            finally:
                os.chmod(project, original)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            output = json.loads(result.stdout)
            self.assertNotIn(
                "additionalContext", output.get("hookSpecificOutput", {})
            )
            self.assertFalse(os.path.exists(os.path.join(project, ".continuity")))


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


def run_hook_in_process(cwd):
    """Drive main() over a stdin payload and return the parsed output."""
    stdout = io.StringIO()
    with mock_stdio(io.StringIO(json.dumps({"session_id": "s", "cwd": cwd})), stdout):
        session_start.main()
    return json.loads(stdout.getvalue())


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


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
