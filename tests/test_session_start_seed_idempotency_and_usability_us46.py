"""tests/test_session_start_seed_idempotency_and_usability_us46.py — CONTINUI-46.

Covers four claims about the eager-seed path that the other CONTINUI-46 test
files touch individually but do not pin down together:

  1. multiple *consecutive* SessionStarts (three in a row, not just two) never
     re-seed an existing store, and `seed_store` is provably not invoked on
     any call after the first
  2. every seed file that carries a timestamp — state.md's `{updated_at}`
     template placeholder, and metadata.json's `created_at` field — is filled
     with a real, parseable, freshly-stamped UTC time, not a leftover literal
  3. `metadata_check_and_migrate` (the schema compatibility gate every other
     read/write path runs through first) passes cleanly over a store this
     hook just seeded, with nothing logged to errors.log
  4. the seeded store is immediately usable by `write_memory()` — a
     checkpoint can be consolidated into it without seeding running again in
     any way that touches already-seeded content
"""

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

import lib.migrate as migrate_module
from lib.migrate import CURRENT_SCHEMA_VERSION, SEED_FILES, metadata_check_and_migrate
from lib.write_memory import write_memory

SESSION_START_HOOK = os.path.join(REPO_ROOT, "hooks", "session-start.py")

_SPEC = importlib.util.spec_from_file_location(
    "session_start_idempotency_us46", SESSION_START_HOOK
)
session_start = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(session_start)


def run_hook_in_process(cwd):
    """Drive main() the way it is actually invoked, over a stdin payload."""
    import io

    stdin = io.StringIO(json.dumps({"session_id": "s", "cwd": cwd}))
    stdout = io.StringIO()
    orig_stdin, orig_stdout = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = stdin, stdout
    try:
        code = session_start.main()
    finally:
        sys.stdin, sys.stdout = orig_stdin, orig_stdout
    return code, json.loads(stdout.getvalue())


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def read_errors_log(store):
    path = os.path.join(store, "errors.log")
    if not os.path.exists(path):
        return ""
    return read(path)


def snapshot(store):
    result = {}
    for name in os.listdir(store):
        path = os.path.join(store, name)
        if os.path.isfile(path):
            result[name] = (read(path), os.stat(path).st_mtime_ns)
    return result


class TestConsecutiveSessionStartsNeverReseed(unittest.TestCase):
    def test_seed_store_is_not_invoked_on_the_second_or_third_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")

            code, _output = run_hook_in_process(tmp)  # first call: real seed
            self.assertEqual(code, 0)
            self.assertTrue(os.path.isdir(store))

            with patch.object(session_start, "seed_store") as seed_store_mock:
                code, _output = run_hook_in_process(tmp)  # second call
                self.assertEqual(code, 0)
                code, _output = run_hook_in_process(tmp)  # third call
                self.assertEqual(code, 0)

            seed_store_mock.assert_not_called()

    def test_store_contents_are_identical_across_three_consecutive_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")

            run_hook_in_process(tmp)
            after_first = snapshot(store)
            self.assertTrue(after_first, "store must be seeded after the first call")

            run_hook_in_process(tmp)
            after_second = snapshot(store)

            run_hook_in_process(tmp)
            after_third = snapshot(store)

            self.assertEqual(after_first, after_second)
            self.assertEqual(after_second, after_third)


class TestTimestampPlaceholderSubstitution(unittest.TestCase):
    def test_state_md_updated_at_is_a_real_recent_utc_timestamp(self):
        before = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)
            after = datetime.now(timezone.utc).replace(microsecond=0)

            state = read(os.path.join(tmp, ".continuity", "state.md"))
            self.assertNotIn("{updated_at}", state)

            match = None
            for line in state.splitlines():
                if line.startswith("updated_at:"):
                    match = line.split("updated_at:", 1)[1].strip()
            self.assertIsNotNone(match, "no updated_at line found in state.md")

            parsed = datetime.strptime(match, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            self.assertGreaterEqual(parsed, before)
            self.assertLessEqual(parsed, after)

    def test_metadata_json_created_at_is_a_real_recent_utc_timestamp(self):
        before = datetime.now(timezone.utc).replace(microsecond=0)
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)
            after = datetime.now(timezone.utc).replace(microsecond=0)

            metadata = json.loads(read(os.path.join(tmp, ".continuity", "metadata.json")))
            created_at = metadata["created_at"]
            self.assertNotEqual(created_at, "")

            parsed = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
            self.assertGreaterEqual(parsed, before)
            self.assertLessEqual(parsed, after)

    def test_only_state_md_carries_the_brace_style_placeholder(self):
        """decisions.md, tasks.md, learnings.md have no timestamp of their
        own to substitute — confirms the placeholder check above isn't
        vacuously true for files that never had one."""
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)

            store = os.path.join(tmp, ".continuity")
            for name in ("decisions.md", "tasks.md", "learnings.md"):
                content = read(os.path.join(store, name))
                self.assertNotRegex(content, r"\{[a-zA-Z_]+\}")


class TestSchemaCompatibilityPassesForSeededStore(unittest.TestCase):
    def test_metadata_check_and_migrate_returns_true_for_a_freshly_seeded_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)

            store = os.path.join(tmp, ".continuity")
            self.assertTrue(metadata_check_and_migrate(store))

    def test_seeded_schema_version_matches_current_and_migration_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)

            store = os.path.join(tmp, ".continuity")
            before = read(os.path.join(store, "metadata.json"))

            metadata = json.loads(before)
            self.assertEqual(metadata["schema_version"], CURRENT_SCHEMA_VERSION)

            self.assertTrue(metadata_check_and_migrate(store))
            after = read(os.path.join(store, "metadata.json"))
            self.assertEqual(before, after, "a current-schema store must not be rewritten")

    def test_a_second_session_start_over_a_seeded_store_logs_no_unsupported_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)
            run_hook_in_process(tmp)  # exercises the metadata_check_and_migrate branch

            store = os.path.join(tmp, ".continuity")
            log = read_errors_log(store)
            self.assertNotIn("unsupported-schema", log)
            self.assertNotIn("corrupted", log)


class TestSeededStoreIsUsableByWriteMemoryWithoutReseeding(unittest.TestCase):
    def test_write_memory_consolidates_a_staged_note_into_the_seeded_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)  # seed via SessionStart, not write_memory

            store = os.path.join(tmp, ".continuity")
            staged_dir = os.path.join(store, ".staged")
            os.makedirs(staged_dir)
            with open(
                os.path.join(staged_dir, "decision-20260101T000000Z-1.md"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write("# Use SQLite for the cache\n\nBecause it needs no server.\n")

            handoff_path = write_memory(tmp, "manual")

            self.assertIsNotNone(handoff_path)
            self.assertTrue(os.path.isfile(handoff_path))

            decisions = read(os.path.join(store, "decisions.md"))
            self.assertTrue(decisions.startswith("# Decisions"))
            self.assertIn("Use SQLite for the cache", decisions)

    def test_write_memory_does_not_clobber_the_already_seeded_state_md(self):
        """seed_store is called unconditionally inside write_memory(), but it
        must remain a strict no-op over files SessionStart already created —
        state.md is untouched by write_memory itself, so it is the clearest
        witness that re-seeding never overwrites."""
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)

            store = os.path.join(tmp, ".continuity")
            state_before = read(os.path.join(store, "state.md"))

            staged_dir = os.path.join(store, ".staged")
            os.makedirs(staged_dir)
            with open(
                os.path.join(staged_dir, "task-20260101T000000Z-1.md"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write("# Wire up the cache\n\nStill pending.\n")

            write_memory(tmp, "manual")

            state_after = read(os.path.join(store, "state.md"))
            self.assertEqual(state_before, state_after)

    def test_write_memory_needs_no_prior_metadata_ensure_call_of_its_own(self):
        """The store already has metadata.json from SessionStart; calling
        write_memory over it must not raise or silently no-op just because
        seeding already happened once."""
        with tempfile.TemporaryDirectory() as tmp:
            run_hook_in_process(tmp)

            store = os.path.join(tmp, ".continuity")
            metadata_before = read(os.path.join(store, "metadata.json"))

            staged_dir = os.path.join(store, ".staged")
            os.makedirs(staged_dir)
            with open(
                os.path.join(staged_dir, "learning-20260101T000000Z-1.md"),
                "w",
                encoding="utf-8",
            ) as handle:
                handle.write("# Locks are advisory, mkdir-based\n\nNo flock on this fs.\n")

            handoff_path = write_memory(tmp, "manual")

            self.assertIsNotNone(handoff_path)
            metadata_after = read(os.path.join(store, "metadata.json"))
            self.assertEqual(metadata_before, metadata_after)


if __name__ == "__main__":
    unittest.main()
