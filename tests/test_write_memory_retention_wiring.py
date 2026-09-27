"""tests/test_write_memory_retention_wiring.py — T032's wiring contract.

Covers three properties of `write_memory`'s call into `retention_prune` that
`tests/test_write_memory_basic.py` does not already pin down:

  13. the store lock is still held while the prune runs (no window where a
      concurrent writer could interleave with it)
  14. prune fires only after `_consolidate` succeeds, never from one of
      `write_memory`'s early returns (nothing staged, unsupported schema,
      lock unavailable)
  15. missing or malformed retention metadata does not crash the prune
"""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.lock import lock_path
from lib.write_memory import staged_dir, write_memory


def stage(project_root, kind, body, suffix="20260912T140501Z-4242"):
    path = os.path.join(
        project_root, ".continuity", ".staged", "{}-{}.md".format(kind, suffix)
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


class TestPruneRunsUnderTheLock(unittest.TestCase):
    def test_the_lock_directory_still_exists_while_prune_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Kept\n\nBody.\n")
            store = os.path.join(tmp, ".continuity")
            seen = {}

            def fake_prune(continuity_dir_path):
                seen["lock_held"] = os.path.isdir(lock_path(continuity_dir_path))

            with mock.patch("lib.write_memory.retention_prune", side_effect=fake_prune):
                write_memory(tmp, "file-change")

            self.assertTrue(seen.get("lock_held"), "prune ran without the store lock")
            # And released once write_memory returns, same as any other run.
            self.assertFalse(os.path.isdir(lock_path(store)))


class TestPruneOnlyAfterASuccessfulConsolidate(unittest.TestCase):
    def test_nothing_staged_never_calls_prune(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(staged_dir(os.path.join(tmp, ".continuity")))

            with mock.patch("lib.write_memory.retention_prune") as prune:
                self.assertIsNone(write_memory(tmp, "session-end"))

            prune.assert_not_called()

    def test_unsupported_schema_never_calls_prune(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Not written\n\nBody.\n")
            store = os.path.join(tmp, ".continuity")
            with open(os.path.join(store, "metadata.json"), "w", encoding="utf-8") as handle:
                json.dump({"schema_version": "9.0", "plugin_version": "9.0.0"}, handle)

            with mock.patch("lib.write_memory.retention_prune") as prune:
                self.assertIsNone(write_memory(tmp, "file-change"))

            prune.assert_not_called()

    def test_lock_unavailable_never_calls_prune(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Not written\n\nBody.\n")
            store = os.path.join(tmp, ".continuity")

            with mock.patch("lib.write_memory.lock_acquire", return_value=False):
                with mock.patch("lib.write_memory.retention_prune") as prune:
                    self.assertIsNone(write_memory(tmp, "file-change"))

            prune.assert_not_called()
            self.assertFalse(os.path.exists(os.path.join(store, "decisions.md")))

    def test_a_successful_consolidate_calls_prune_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Kept\n\nBody.\n")

            with mock.patch("lib.write_memory.retention_prune") as prune:
                handoff_path = write_memory(tmp, "file-change")

            self.assertIsNotNone(handoff_path)
            prune.assert_called_once()


class TestMissingOrIncompleteRetentionMetadataDoesNotCrash(unittest.TestCase):
    def test_no_metadata_json_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Kept\n\nBody.\n")
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store, exist_ok=True)
            metadata_path = os.path.join(store, "metadata.json")
            self.assertFalse(os.path.exists(metadata_path))

            handoff_path = write_memory(tmp, "file-change")

            self.assertIsNotNone(handoff_path)
            self.assertFalse(
                os.path.exists(os.path.join(store, "errors.log")),
                "a missing metadata.json falls back to defaults, not a logged failure",
            )

    def test_metadata_json_present_but_missing_retention_days(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Kept\n\nBody.\n")
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store, exist_ok=True)
            with open(os.path.join(store, "metadata.json"), "w", encoding="utf-8") as handle:
                json.dump({"schema_version": "1.0", "plugin_version": "1.0.0"}, handle)

            handoff_path = write_memory(tmp, "file-change")

            self.assertIsNotNone(handoff_path)
            self.assertTrue(os.path.exists(handoff_path))

    def test_metadata_json_with_wrong_typed_retention_days_falls_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Kept\n\nBody.\n")
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store, exist_ok=True)
            with open(os.path.join(store, "metadata.json"), "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "schema_version": "1.0",
                        "plugin_version": "1.0.0",
                        "retention_days": "not-a-number",
                    },
                    handle,
                )

            handoff_path = write_memory(tmp, "file-change")

            self.assertIsNotNone(handoff_path)

    def test_metadata_json_is_corrupt_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Kept\n\nBody.\n")
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store, exist_ok=True)
            with open(os.path.join(store, "metadata.json"), "w", encoding="utf-8") as handle:
                handle.write("{not valid json")

            # metadata_check_and_migrate reads metadata.json too; corrupt JSON
            # there is a pre-existing concern of T029/migrate, not this
            # wiring — so exercise retention_prune directly against a store
            # whose metadata.json is corrupt, standing in for a store that
            # got past the earlier check (e.g. corrupted between the two
            # reads) to prove the prune call itself tolerates it.
            from lib.retention import retention_prune

            try:
                retention_prune(store)
            except Exception as error:  # noqa: BLE001
                self.fail("retention_prune raised on corrupt metadata.json: {}".format(error))


if __name__ == "__main__":
    unittest.main()
