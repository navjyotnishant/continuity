"""tests/test_migrate.py — unit tests for lib/migrate.py.

The three cases tasks.md T012 names are TestCheckAndMigrate's first three:
a store at the current schema version is left alone, a store at the prior
version gains the current `schema_version`, and a store at an unsupported
newer version is byte-for-byte unchanged with an `unsupported-schema` line
in `errors.log`.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

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

    def test_missing_schema_version_returns_false_and_logs_without_rewriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            os.makedirs(continuity_dir)
            path = os.path.join(continuity_dir, "metadata.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"plugin_version": "0.1.0"}, handle)
            before = _read_bytes(path)

            self.assertFalse(metadata_check_and_migrate(continuity_dir))

            self.assertEqual(_read_bytes(path), before)
            self.assertIn("corrupted", _errors_log(continuity_dir))

    def test_newer_minor_of_current_major_is_not_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, "1.7")
            before = _read_bytes(path)

            self.assertTrue(metadata_check_and_migrate(continuity_dir))

            self.assertEqual(_read_bytes(path), before)
            self.assertEqual(_errors_log(continuity_dir), "")

    @unittest.skipIf(os.geteuid() == 0, "root bypasses file permission checks")
    def test_unreadable_metadata_json_fails_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, CURRENT_SCHEMA_VERSION)
            before = _read_bytes(path)
            os.chmod(path, 0o000)
            try:
                self.assertFalse(metadata_check_and_migrate(continuity_dir))
            finally:
                os.chmod(path, 0o644)

            self.assertEqual(_read_bytes(path), before)
            self.assertIn("corrupted", _errors_log(continuity_dir))

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permission checks")
    def test_write_denied_during_migration_fails_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, PRIOR_SCHEMA_VERSION)
            before = _read_bytes(path)
            os.chmod(continuity_dir, 0o555)
            try:
                self.assertFalse(metadata_check_and_migrate(continuity_dir))
            finally:
                os.chmod(continuity_dir, 0o755)

            # No errors.log assertion here: .continuity/ itself is read-only, so
            # continuity_log()'s own append into it silently no-ops too — the
            # documented exception in data-model.md. Fail-open stays observable
            # as the False return plus metadata.json left byte-for-byte intact.
            self.assertEqual(_read_bytes(path), before)

            # The finally block's chmod ran despite the operation above having
            # failed; confirm the directory is actually writable again rather
            # than trusting that os.chmod raised nothing.
            probe_path = os.path.join(continuity_dir, "write_probe")
            with open(probe_path, "w", encoding="utf-8") as handle:
                handle.write("probe")
            self.assertTrue(os.path.isfile(probe_path))

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permission checks")
    def test_write_denied_metadata_json_stays_readable_and_parseable(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, PRIOR_SCHEMA_VERSION)
            before = _read_json(path)
            os.chmod(continuity_dir, 0o555)
            try:
                self.assertFalse(metadata_check_and_migrate(continuity_dir))

                # A read-only directory still permits reading its existing
                # files; metadata.json must still open and parse as the
                # untouched, prior-version document.
                after = _read_json(path)
            finally:
                os.chmod(continuity_dir, 0o755)

            self.assertEqual(after, before)
            self.assertEqual(after["schema_version"], PRIOR_SCHEMA_VERSION)

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permission checks")
    def test_write_denied_fail_open_contract_observable_without_errors_log(self):
        # Covers the fail-open contract from a write-denied .continuity/ dir
        # without relying on errors.log, which continuity_log() cannot write
        # into for the same reason migration itself cannot: the directory is
        # read-only. False return + byte-for-byte unchanged file are the
        # only observable guarantees here.
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, PRIOR_SCHEMA_VERSION)
            before = _read_bytes(path)
            os.chmod(continuity_dir, 0o555)
            try:
                result = metadata_check_and_migrate(continuity_dir)
            finally:
                os.chmod(continuity_dir, 0o755)

            self.assertIs(result, False)
            self.assertEqual(_read_bytes(path), before)

    def test_write_denied_comment_matches_continuity_log_contract(self):
        # The comment above explains why no errors.log assertion is made:
        # continuity_log()'s own append silently no-ops when it can't write.
        # Verify that claim directly against the documented contract instead
        # of trusting the prose: continuity_log() must not raise, and must
        # leave errors.log absent, when continuity_dir_path is unwritable.
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            os.makedirs(continuity_dir)
            os.chmod(continuity_dir, 0o555)
            try:
                try:
                    migrate.continuity_log(
                        continuity_dir, "migrate", "write-failed", "detail"
                    )
                except Exception as exc:  # noqa: BLE001 -- must fail open
                    self.fail(
                        "continuity_log() raised {!r} instead of silently "
                        "no-opping".format(exc)
                    )
            finally:
                os.chmod(continuity_dir, 0o755)

            self.assertFalse(os.path.isfile(os.path.join(continuity_dir, "errors.log")))

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permission checks")
    def test_write_denied_during_migration_raises_no_exception(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            _write_metadata(continuity_dir, PRIOR_SCHEMA_VERSION)
            os.chmod(continuity_dir, 0o555)
            try:
                metadata_check_and_migrate(continuity_dir)
            except Exception as exc:  # noqa: BLE001 -- fail-open means never raise
                self.fail("metadata_check_and_migrate() raised {!r}".format(exc))
            finally:
                os.chmod(continuity_dir, 0o755)

    def test_write_denied_returns_false(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            _write_metadata(continuity_dir, PRIOR_SCHEMA_VERSION)
            os.chmod(continuity_dir, 0o555)
            try:
                self.assertFalse(metadata_check_and_migrate(continuity_dir))
            finally:
                os.chmod(continuity_dir, 0o755)

    def test_write_denied_leaves_metadata_byte_for_byte_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, PRIOR_SCHEMA_VERSION)
            before = _read_bytes(path)
            os.chmod(continuity_dir, 0o555)
            try:
                metadata_check_and_migrate(continuity_dir)
            finally:
                os.chmod(continuity_dir, 0o755)

            self.assertEqual(_read_bytes(path), before)

    def test_unreadable_metadata_still_logs_when_continuity_dir_stays_writable(self):
        # Contrast case for the write-denied tests above: here only
        # metadata.json itself is made unreadable, .continuity/ is never
        # chmodded, so continuity_log() can still append and errors.log's
        # content assertion is legitimate rather than incidental.
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, CURRENT_SCHEMA_VERSION)
            os.chmod(path, 0o000)
            try:
                self.assertFalse(metadata_check_and_migrate(continuity_dir))
            finally:
                os.chmod(path, 0o644)

            self.assertTrue(os.access(continuity_dir, os.W_OK))
            self.assertIn("corrupted", _errors_log(continuity_dir))

    def test_migration_success_leaves_no_temporary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            _write_metadata(continuity_dir, PRIOR_SCHEMA_VERSION)

            self.assertTrue(metadata_check_and_migrate(continuity_dir))

            entries = sorted(os.listdir(continuity_dir))
            self.assertEqual(entries, ["metadata.json"])
            self.assertFalse(any(name.startswith("metadata.json.tmp") for name in entries))

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permission checks")
    def test_migration_failure_leaves_no_temporary_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            _write_metadata(continuity_dir, PRIOR_SCHEMA_VERSION)
            os.chmod(continuity_dir, 0o555)
            try:
                self.assertFalse(metadata_check_and_migrate(continuity_dir))
                entries = os.listdir(continuity_dir)
            finally:
                os.chmod(continuity_dir, 0o755)

            self.assertFalse(any(name.startswith("metadata.json.tmp") for name in entries))

    def test_all_error_conditions_log_operation_and_reason_fields(self):
        scenarios = []

        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            os.makedirs(continuity_dir)
            with open(
                os.path.join(continuity_dir, "metadata.json"), "w", encoding="utf-8"
            ) as handle:
                handle.write("{ not json")
            self.assertFalse(metadata_check_and_migrate(continuity_dir))
            scenarios.append((_errors_log(continuity_dir), "corrupted"))

        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            _write_metadata(continuity_dir, UNSUPPORTED_NEWER_SCHEMA_VERSION)
            self.assertFalse(metadata_check_and_migrate(continuity_dir))
            scenarios.append((_errors_log(continuity_dir), "unsupported-schema"))

        for log, reason in scenarios:
            lines = [line for line in log.splitlines() if line]
            self.assertEqual(len(lines), 1)
            fields = lines[0].split("|")
            self.assertEqual(len(fields), 4)
            timestamp, operation, failure_kind, _detail = (
                field.strip() for field in fields
            )
            self.assertEqual(operation, "migrate")
            self.assertEqual(failure_kind, reason)
            self.assertTrue(timestamp)

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

    def test_created_at_is_a_valid_iso8601_utc_timestamp(self):
        import datetime as _datetime

        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")

            self.assertTrue(metadata_ensure(continuity_dir))

            metadata = _read_json(os.path.join(continuity_dir, "metadata.json"))
            created_at = metadata["created_at"]
            self.assertTrue(created_at.endswith("Z"))
            # Raises ValueError if the timestamp doesn't actually parse.
            _datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ")

    def test_creates_continuity_dir_when_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            self.assertFalse(os.path.isdir(continuity_dir))

            self.assertTrue(metadata_ensure(continuity_dir))

            self.assertTrue(os.path.isdir(continuity_dir))

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

    def test_corrupted_template_fails_open_and_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            bad_template = os.path.join(tmp, "bad.json.tmpl")
            with open(bad_template, "w", encoding="utf-8") as handle:
                handle.write("{ not json")

            original = migrate.METADATA_TEMPLATE_PATH
            migrate.METADATA_TEMPLATE_PATH = bad_template
            try:
                self.assertFalse(metadata_ensure(continuity_dir))
            finally:
                migrate.METADATA_TEMPLATE_PATH = original

            self.assertFalse(
                os.path.exists(os.path.join(continuity_dir, "metadata.json"))
            )
            self.assertIn("corrupted", _errors_log(continuity_dir))

    def test_non_dict_template_root_fails_open_and_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            list_template = os.path.join(tmp, "list.json.tmpl")
            with open(list_template, "w", encoding="utf-8") as handle:
                json.dump(["schema_version", "1.0"], handle)

            original = migrate.METADATA_TEMPLATE_PATH
            migrate.METADATA_TEMPLATE_PATH = list_template
            try:
                self.assertFalse(metadata_ensure(continuity_dir))
            finally:
                migrate.METADATA_TEMPLATE_PATH = original

            self.assertFalse(
                os.path.exists(os.path.join(continuity_dir, "metadata.json"))
            )
            self.assertIn("corrupted", _errors_log(continuity_dir))

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permission checks")
    def test_denied_continuity_dir_write_fails_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            # metadata_ensure must create continuity_dir itself; a read-only
            # parent means os.makedirs() cannot create it.
            os.chmod(tmp, 0o555)
            try:
                self.assertFalse(metadata_ensure(continuity_dir))
                self.assertFalse(os.path.isdir(continuity_dir))
            finally:
                os.chmod(tmp, 0o755)

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permission checks")
    def test_denied_metadata_json_write_fails_open(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            os.makedirs(continuity_dir)
            os.chmod(continuity_dir, 0o555)
            try:
                self.assertFalse(metadata_ensure(continuity_dir))
                self.assertFalse(
                    os.path.exists(os.path.join(continuity_dir, "metadata.json"))
                )
            finally:
                os.chmod(continuity_dir, 0o755)

    def test_leaves_no_temp_debris_on_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")

            self.assertTrue(metadata_ensure(continuity_dir))

            self.assertEqual(sorted(os.listdir(continuity_dir)), ["metadata.json"])

    @unittest.skipIf(os.geteuid() == 0, "root bypasses directory permission checks")
    def test_leaves_no_temp_debris_on_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            os.makedirs(continuity_dir)
            os.chmod(continuity_dir, 0o555)
            try:
                self.assertFalse(metadata_ensure(continuity_dir))
                self.assertEqual(os.listdir(continuity_dir), [])
            finally:
                os.chmod(continuity_dir, 0o755)

    def test_check_and_migrate_current_version_returns_true_unmodified(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, CURRENT_SCHEMA_VERSION)
            before = _read_bytes(path)

            self.assertTrue(metadata_check_and_migrate(continuity_dir))

            self.assertEqual(_read_bytes(path), before)
            self.assertEqual(_errors_log(continuity_dir), "")


class TestLoggingTruncation(unittest.TestCase):
    def test_error_log_does_not_expose_raw_values_over_40_chars(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            huge_version = "9" * 5000
            _write_metadata(continuity_dir, huge_version)

            self.assertFalse(metadata_check_and_migrate(continuity_dir))

            log = _errors_log(continuity_dir)
            self.assertIn("unsupported-schema", log)
            # The raw schema_version must be truncated before logging, not
            # dumped in full: no run of the raw value's repeated digit should
            # survive past the ~40-char truncation contract.
            self.assertNotIn("9" * 41, log)


class TestSchemaVersionExtraction(unittest.TestCase):
    def test_non_numeric_major_fails_gracefully(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, "abc.0")
            before = _read_bytes(path)

            self.assertFalse(metadata_check_and_migrate(continuity_dir))

            self.assertEqual(_read_bytes(path), before)
            self.assertIn("corrupted", _errors_log(continuity_dir))

    def test_version_with_extra_components_uses_leading_major(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            major = CURRENT_SCHEMA_VERSION.split(".")[0]
            path = _write_metadata(continuity_dir, "{}.0.0".format(major))
            before = _read_bytes(path)

            self.assertTrue(metadata_check_and_migrate(continuity_dir))

            # Same major as current (extra components ignored): left as-is,
            # same treatment as any other same-major store.
            self.assertEqual(_read_bytes(path), before)
            self.assertEqual(_errors_log(continuity_dir), "")


class TestMigrationForwardScope(unittest.TestCase):
    def test_migration_updates_only_schema_version_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(
                continuity_dir, PRIOR_SCHEMA_VERSION, extra_field="untouched"
            )
            before = _read_json(path)

            self.assertTrue(metadata_check_and_migrate(continuity_dir))

            after = _read_json(path)
            self.assertEqual(after["schema_version"], CURRENT_SCHEMA_VERSION)
            # Every other field, including one the code doesn't know about,
            # must survive byte-for-byte: no format changes yet per contract.
            unchanged = dict(before)
            del unchanged["schema_version"]
            after_minus_version = dict(after)
            del after_minus_version["schema_version"]
            self.assertEqual(after_minus_version, unchanged)


class TestAtomicWriteCrashSafety(unittest.TestCase):
    def test_crash_during_migration_write_leaves_original_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            path = _write_metadata(continuity_dir, PRIOR_SCHEMA_VERSION)
            before = _read_bytes(path)

            with mock.patch(
                "lib.migrate.atomic_write", side_effect=OSError("simulated crash")
            ):
                self.assertFalse(metadata_check_and_migrate(continuity_dir))

            # A crash mid-write must never leave a half-written or corrupted
            # metadata.json: the file on disk is exactly what it was before.
            self.assertEqual(_read_bytes(path), before)
            self.assertIn("write-failed", _errors_log(continuity_dir))

    def test_crash_during_ensure_write_leaves_no_metadata_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")

            with mock.patch(
                "lib.migrate.atomic_write", side_effect=OSError("simulated crash")
            ):
                self.assertFalse(metadata_ensure(continuity_dir))

            self.assertFalse(
                os.path.exists(os.path.join(continuity_dir, "metadata.json"))
            )
            self.assertIn("write-failed", _errors_log(continuity_dir))


class TestCreatedAtNotCached(unittest.TestCase):
    def test_created_at_differs_between_separate_ensure_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            first_dir = os.path.join(tmp, "first", ".continuity")
            second_dir = os.path.join(tmp, "second", ".continuity")

            with mock.patch(
                "lib.migrate._utc_now", return_value="2026-01-01T00:00:00Z"
            ):
                self.assertTrue(metadata_ensure(first_dir))

            with mock.patch(
                "lib.migrate._utc_now", return_value="2026-06-15T12:30:00Z"
            ):
                self.assertTrue(metadata_ensure(second_dir))

            first_metadata = _read_json(os.path.join(first_dir, "metadata.json"))
            second_metadata = _read_json(os.path.join(second_dir, "metadata.json"))
            # created_at must be computed at call time, not a cached or
            # hardcoded constant shared across calls.
            self.assertNotEqual(
                first_metadata["created_at"], second_metadata["created_at"]
            )
            self.assertEqual(first_metadata["created_at"], "2026-01-01T00:00:00Z")
            self.assertEqual(second_metadata["created_at"], "2026-06-15T12:30:00Z")


class TestNewMetadataFieldsFromTemplate(unittest.TestCase):
    def test_new_metadata_includes_all_template_fields_except_code_set_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            continuity_dir = os.path.join(tmp, ".continuity")
            template_path = os.path.join(tmp, "metadata.json.tmpl")
            template_content = {
                "schema_version": "0.0",
                "plugin_version": "0.1.0",
                "created_at": "1970-01-01T00:00:00Z",
                "retention_days": 45,
                "git_tracked": False,
            }
            with open(template_path, "w", encoding="utf-8") as handle:
                json.dump(template_content, handle)

            original = migrate.METADATA_TEMPLATE_PATH
            migrate.METADATA_TEMPLATE_PATH = template_path
            try:
                self.assertTrue(metadata_ensure(continuity_dir))
            finally:
                migrate.METADATA_TEMPLATE_PATH = original

            metadata = _read_json(os.path.join(continuity_dir, "metadata.json"))

            # Every template field not owned by code must pass through as-is.
            for key, value in template_content.items():
                if key in ("schema_version", "created_at"):
                    continue
                self.assertIn(key, metadata)
                self.assertEqual(metadata[key], value)

            # schema_version and created_at are the code's own, not the
            # template's placeholder values.
            self.assertEqual(metadata["schema_version"], CURRENT_SCHEMA_VERSION)
            self.assertNotEqual(
                metadata["created_at"], template_content["created_at"]
            )

            # No fields beyond the template's own plus nothing invented.
            self.assertEqual(set(metadata.keys()), set(template_content.keys()))


class TestModuleExitsClean(unittest.TestCase):
    # Guard against the subprocess below re-running this very test: without
    # it, the child's `-m unittest tests.test_migrate` invocation would hit
    # this same test, spawning a grandchild, recursing until each level
    # times out.
    @unittest.skipIf(
        os.environ.get("_CONTINUITY_SKIP_MODULE_EXIT_TEST") == "1",
        "nested invocation from the subprocess under test",
    )
    def test_module_run_via_unittest_exits_0(self):
        env = dict(os.environ, _CONTINUITY_SKIP_MODULE_EXIT_TEST="1")
        result = subprocess.run(
            [sys.executable, "-m", "unittest", "tests.test_migrate"],
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        self.assertEqual(
            result.returncode, 0, msg=result.stdout + result.stderr
        )


if __name__ == "__main__":
    unittest.main()
