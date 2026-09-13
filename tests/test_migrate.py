"""tests/test_migrate.py — metadata.json creation and schema compatibility
(T012, contracts/file-format-contract.md -> metadata.json).

Covers `metadata_ensure` (creates the file from the seed template when
absent) and `metadata_check_and_migrate` (current schema read unchanged,
an older-but-supported schema migrated forward in place, an unsupported
newer schema fails open with no write at all).
"""

import json
import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.migrate import SCHEMA_VERSION, metadata_check_and_migrate, metadata_ensure


def read_metadata(continuity_dir_path):
    with open(
        os.path.join(continuity_dir_path, "metadata.json"), encoding="utf-8"
    ) as handle:
        return json.load(handle)


class TestMetadataEnsure(unittest.TestCase):
    def test_creates_metadata_json_from_the_template_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)

            self.assertTrue(metadata_ensure(store))

            metadata = read_metadata(store)
            self.assertEqual(metadata["schema_version"], "1.0")
            self.assertIn("plugin_version", metadata)
            self.assertTrue(metadata["created_at"])

    def test_does_not_overwrite_an_existing_metadata_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            target = os.path.join(store, "metadata.json")
            with open(target, "w", encoding="utf-8") as handle:
                json.dump({"schema_version": "1.0", "plugin_version": "9.9.9"}, handle)

            self.assertTrue(metadata_ensure(store))

            self.assertEqual(read_metadata(store)["plugin_version"], "9.9.9")


class TestSchemaCompatibility(unittest.TestCase):
    def test_current_schema_version_is_read_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            target = os.path.join(store, "metadata.json")
            original = {
                "schema_version": SCHEMA_VERSION,
                "plugin_version": "0.1.0",
                "created_at": "2026-01-01T00:00:00Z",
                "retention_days": 60,
                "git_tracked": True,
            }
            with open(target, "w", encoding="utf-8") as handle:
                json.dump(original, handle)
            with open(target, encoding="utf-8") as handle:
                before = handle.read()

            self.assertTrue(metadata_check_and_migrate(store))

            with open(target, encoding="utf-8") as handle:
                after = handle.read()
            self.assertEqual(before, after, "current schema must not be rewritten")

    def test_absent_metadata_json_is_treated_as_current_and_safe_to_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            # Other store files exist but metadata.json does not -- the
            # pre-metadata.json "1.0" case (contract's Q9 backward-compat
            # rule).
            with open(os.path.join(store, "decisions.md"), "w", encoding="utf-8") as handle:
                handle.write("# Decision: x\n\n```\ncaptured_at: 1\ncategory: decision\n```\n\nBody.\n")

            self.assertTrue(metadata_check_and_migrate(store))
            self.assertFalse(os.path.exists(os.path.join(store, "metadata.json")))

    def test_older_but_supported_schema_is_migrated_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            target = os.path.join(store, "metadata.json")
            with open(target, "w", encoding="utf-8") as handle:
                json.dump(
                    {"schema_version": "0.9", "plugin_version": "0.0.9"}, handle
                )

            self.assertTrue(metadata_check_and_migrate(store))

            migrated = read_metadata(store)
            self.assertEqual(migrated["schema_version"], SCHEMA_VERSION)
            # Migration rewrites the version marker in place; it must not
            # invent or drop other fields.
            self.assertEqual(migrated["plugin_version"], "0.0.9")

    def test_unsupported_newer_schema_fails_open_with_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            target = os.path.join(store, "metadata.json")
            with open(target, "w", encoding="utf-8") as handle:
                json.dump({"schema_version": "9.0", "plugin_version": "9.0.0"}, handle)
            with open(target, encoding="utf-8") as handle:
                before = handle.read()

            self.assertFalse(metadata_check_and_migrate(store))

            with open(target, encoding="utf-8") as handle:
                after = handle.read()
            self.assertEqual(before, after, "an unsupported schema must not be modified")

            with open(os.path.join(store, "errors.log"), encoding="utf-8") as handle:
                self.assertIn("unsupported-schema", handle.read())


if __name__ == "__main__":
    unittest.main()
