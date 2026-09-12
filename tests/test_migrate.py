"""tests/test_migrate.py — unit tests for lib/migrate.py.

The three cases tasks.md T012 names are TestCheckAndMigrate's first three:
a store at the current schema version is left alone, a store at the prior
version gains the current `schema_version`, and a store at an unsupported
newer version is byte-for-byte unchanged with an `unsupported-schema` line
in `errors.log`.
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib import migrate
from lib.migrate import (
    CURRENT_SCHEMA_VERSION,
    metadata_check_and_migrate,
    metadata_ensure,
)

PRIOR_SCHEMA_VERSION = "0.9"
UNSUPPORTED_NEWER_SCHEMA_VERSION = "2.0"


def _write_metadata(continuity_dir, schema_version, **extra):
    os.makedirs(continuity_dir, exist_ok=True)
    metadata = {
        "schema_version": schema_version,
        "plugin_version": "0.1.0",
        "created_at": "2026-09-01T00:00:00Z",
        "retention_days": 45,
        "git_tracked": False,
    }
    metadata.update(extra)
    path = os.path.join(continuity_dir, "metadata.json")
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)
    return path


def _read_json(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def _errors_log(continuity_dir):
    path = os.path.join(continuity_dir, "errors.log")
    if not os.path.isfile(path):
        return ""
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


class TestCheckAndMigrate(unittest.TestCase):
    def test_current_version_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, CURRENT_SCHEMA_VERSION)
            before = _read_bytes(path)

            self.assertTrue(metadata_check_and_migrate(continuity_dir))

            self.assertEqual(_read_bytes(path), before)
            self.assertEqual(_errors_log(continuity_dir), "")

    def test_prior_version_is_migrated_forward(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, PRIOR_SCHEMA_VERSION)

            self.assertTrue(metadata_check_and_migrate(continuity_dir))

            migrated = _read_json(path)
            self.assertEqual(migrated["schema_version"], CURRENT_SCHEMA_VERSION)
            # Migrating forward must not discard the developer's own config.
            self.assertEqual(migrated["retention_days"], 45)
            self.assertEqual(migrated["git_tracked"], False)
            self.assertEqual(migrated["created_at"], "2026-09-01T00:00:00Z")

    def test_prior_version_migration_leaves_no_temp_debris(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            _write_metadata(continuity_dir, PRIOR_SCHEMA_VERSION)

            self.assertTrue(metadata_check_and_migrate(continuity_dir))

            self.assertEqual(sorted(os.listdir(continuity_dir)), ["metadata.json"])

    def test_unsupported_newer_version_is_untouched_and_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(
                continuity_dir, UNSUPPORTED_NEWER_SCHEMA_VERSION, future_field="kept"
            )
            before = _read_bytes(path)

            self.assertFalse(metadata_check_and_migrate(continuity_dir))

            self.assertEqual(_read_bytes(path), before)
            self.assertIn("unsupported-schema", _errors_log(continuity_dir))
            # errors.log is the only write the contract permits here.
            self.assertEqual(
                sorted(os.listdir(continuity_dir)), ["errors.log", "metadata.json"]
            )

    def test_far_older_unmigratable_version_is_untouched_and_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, "-1.0")
            before = _read_bytes(path)

            self.assertFalse(metadata_check_and_migrate(continuity_dir))

            self.assertEqual(_read_bytes(path), before)
            self.assertIn("unsupported-schema", _errors_log(continuity_dir))

    def test_newer_minor_of_same_major_is_readable_and_not_downgraded(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, "1.7")
            before = _read_bytes(path)

            self.assertTrue(metadata_check_and_migrate(continuity_dir))

            self.assertEqual(_read_bytes(path), before)

    def test_absent_metadata_is_treated_as_current_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            os.makedirs(continuity_dir)

            self.assertTrue(metadata_check_and_migrate(continuity_dir))

            self.assertEqual(os.listdir(continuity_dir), [])

    def test_absent_continuity_dir_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(metadata_check_and_migrate(os.path.join(tmp, ".continuity")))

    def test_unparseable_metadata_fails_open_without_rewriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            os.makedirs(continuity_dir)
            path = os.path.join(continuity_dir, "metadata.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("{ not json")

            self.assertFalse(metadata_check_and_migrate(continuity_dir))

            self.assertEqual(_read_bytes(path), b"{ not json")
            self.assertIn("corrupted", _errors_log(continuity_dir))

    def test_missing_schema_version_fails_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            os.makedirs(continuity_dir)
            path = os.path.join(continuity_dir, "metadata.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"plugin_version": "0.1.0"}, handle)

            self.assertFalse(metadata_check_and_migrate(continuity_dir))
            self.assertIn("corrupted", _errors_log(continuity_dir))

    def test_logged_detail_never_carries_a_long_raw_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            _write_metadata(continuity_dir, "9" * 5000)

            self.assertFalse(metadata_check_and_migrate(continuity_dir))

            log = _errors_log(continuity_dir)
            self.assertEqual(log.count("\n"), 1)
            self.assertLess(len(log), 200)


class TestMetadataEnsure(unittest.TestCase):
    def test_creates_metadata_from_the_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")

            self.assertTrue(metadata_ensure(continuity_dir))

            metadata = _read_json(os.path.join(continuity_dir, "metadata.json"))
            self.assertEqual(metadata["schema_version"], CURRENT_SCHEMA_VERSION)
            self.assertIn("plugin_version", metadata)
            # created_at is stamped now, not left as the template's placeholder.
            self.assertTrue(metadata["created_at"].endswith("Z"))
            self.assertTrue(metadata["created_at"][:2].isdigit())
            self.assertEqual(_errors_log(continuity_dir), "")

    def test_leaves_no_temp_debris(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")

            self.assertTrue(metadata_ensure(continuity_dir))

            self.assertEqual(sorted(os.listdir(continuity_dir)), ["metadata.json"])

    def test_does_not_touch_an_existing_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, CURRENT_SCHEMA_VERSION)
            before = _read_bytes(path)

            self.assertTrue(metadata_ensure(continuity_dir))

            self.assertEqual(_read_bytes(path), before)

    def test_does_not_touch_an_unsupported_existing_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, UNSUPPORTED_NEWER_SCHEMA_VERSION)
            before = _read_bytes(path)

            self.assertTrue(metadata_ensure(continuity_dir))

            self.assertEqual(_read_bytes(path), before)

    def test_missing_template_fails_open_and_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            original = migrate.METADATA_TEMPLATE_PATH
            migrate.METADATA_TEMPLATE_PATH = os.path.join(tmp, "absent.json.tmpl")
            try:
                self.assertFalse(metadata_ensure(continuity_dir))
            finally:
                migrate.METADATA_TEMPLATE_PATH = original

            self.assertFalse(
                os.path.exists(os.path.join(continuity_dir, "metadata.json"))
            )
            self.assertIn("missing", _errors_log(continuity_dir))


if __name__ == "__main__":
    unittest.main()
