"""tests/test_session_start_corrupted_store.py — CONTINUI-12 (US2: Never
notice Continuity is running).

FR-012's fail-open guarantee has to hold not just for a *missing*
`.continuity/` (test_session_start_no_history.py) but for a *present and
damaged* one: a prior crash mid-write, a hand-edit, or a bad merge can leave
`state.md`/`decisions.md`/`tasks.md`/`learnings.md`/`metadata.json` non-UTF-8,
truncated, or holding malformed JSON in their frontmatter fence. None of that
may raise out of `hooks/session-start.py`, block the session from starting,
or produce non-JSON stdout — the hook must degrade to "inject nothing" (or
whatever it can still salvage) exactly as it does for FR-007's no-history
case.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

SESSION_START_HOOK = os.path.join(REPO_ROOT, "hooks", "session-start.py")


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(data)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def run_hook(cwd):
    return subprocess.run(
        [sys.executable, SESSION_START_HOOK],
        input=json.dumps({"session_id": "test-session", "cwd": cwd}),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )


class TestCorruptedMetadataJsonDoesNotCrash(unittest.TestCase):
    def test_malformed_metadata_json_is_handled_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write_text(os.path.join(store, "metadata.json"), "{ not valid json ")
            write_text(
                os.path.join(store, "state.md"),
                "# Project State\n\n```\nupdated_at: 2026-09-12T09:00:00Z\n```\n\nSome state.\n",
            )

            result = run_hook(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertEqual(
                payload["hookSpecificOutput"]["hookEventName"], "SessionStart"
            )


class TestNonUtf8DurableFilesDoNotCrash(unittest.TestCase):
    def test_binary_garbage_in_a_durable_file_is_handled_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write_bytes(
                os.path.join(store, "decisions.md"),
                b"\xff\xfe\x00\x01not-utf8-at-all\x80\x81",
            )
            write_text(
                os.path.join(store, "state.md"),
                "# Project State\n\n```\nupdated_at: 2026-09-12T09:00:00Z\n```\n\nSome state.\n",
            )

            result = run_hook(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            # Must still emit a well-formed envelope, whatever it decided to
            # inject (or not) from the unreadable file.
            payload = json.loads(result.stdout)
            self.assertIn("hookSpecificOutput", payload)


class TestTruncatedFrontMatterDoesNotCrash(unittest.TestCase):
    def test_decisions_file_with_an_unterminated_code_fence_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write_text(
                os.path.join(store, "decisions.md"),
                "## Decision: Truncated\n\n```\ncaptured_at: 2026-09-12T10:00:00Z\n"
                "category: decision\n\nNo closing fence and no body follows",
            )
            write_text(
                os.path.join(store, "state.md"),
                "# Project State\n\n```\nupdated_at: 2026-09-12T09:00:00Z\n```\n\nSome state.\n",
            )

            result = run_hook(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            json.loads(result.stdout)  # must still be valid JSON on stdout


class TestEmptyDurableFilesDoNotCrash(unittest.TestCase):
    def test_zero_byte_state_file_is_handled_without_crashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write_text(os.path.join(store, "state.md"), "")
            write_text(os.path.join(store, "decisions.md"), "")

            result = run_hook(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            json.loads(result.stdout)


class TestCorruptedStoreNeverSurfacesAnErrorToTheSession(unittest.TestCase):
    def test_session_proceeds_normally_despite_multiple_corrupted_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            write_text(os.path.join(store, "metadata.json"), "not json at all")
            write_bytes(os.path.join(store, "tasks.md"), b"\x00\x00garbage\xff")
            write_text(os.path.join(store, "learnings.md"), "### malformed heading, no fence")

            result = run_hook(tmp)

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, "")
            payload = json.loads(result.stdout)
            self.assertEqual(
                payload["hookSpecificOutput"]["hookEventName"], "SessionStart"
            )


if __name__ == "__main__":
    unittest.main()
