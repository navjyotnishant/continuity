"""tests/test_common.py — unit tests for lib/common.py."""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.common import continuity_dir, continuity_log, read_metadata_defaults


class TestContinuityDir(unittest.TestCase):
    def test_resolves_under_project_root(self):
        self.assertEqual(
            continuity_dir("/tmp/some-project"),
            os.path.join("/tmp/some-project", ".continuity"),
        )

    def test_strips_trailing_slash(self):
        self.assertEqual(
            continuity_dir("/tmp/some-project/"),
            os.path.join("/tmp/some-project", ".continuity"),
        )


class TestContinuityLog(unittest.TestCase):
    def test_append_creates_dir_and_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, ".continuity")
            continuity_log(target, "session-start", "corrupted", "state.md")

            errors_log = os.path.join(target, "errors.log")
            self.assertTrue(os.path.isfile(errors_log))

            with open(errors_log, encoding="utf-8") as handle:
                line = handle.readline()

            fields = [part.strip() for part in line.split("|")]
            self.assertEqual(len(fields), 4)
            self.assertEqual(fields[1], "session-start")
            self.assertEqual(fields[2], "corrupted")
            self.assertEqual(fields[3], "state.md")

    def test_scrubs_pipes_and_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, ".continuity")
            continuity_log(target, "op", "kind", "line1|has\npipe and newline")

            with open(os.path.join(target, "errors.log"), encoding="utf-8") as handle:
                line = handle.readline()

            self.assertEqual(line.count("\n"), 1)
            fields = line.split("|")
            self.assertEqual(len(fields), 4)


class TestReadMetadataDefaults(unittest.TestCase):
    def test_defaults_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            retention_days, git_tracked = read_metadata_defaults(
                os.path.join(tmp, ".continuity")
            )
            self.assertEqual(retention_days, 60)
            self.assertTrue(git_tracked)

    def test_reads_configured_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, ".continuity")
            os.makedirs(target)
            with open(os.path.join(target, "metadata.json"), "w", encoding="utf-8") as handle:
                json.dump({"retention_days": 30, "git_tracked": False}, handle)

            retention_days, git_tracked = read_metadata_defaults(target)
            self.assertEqual(retention_days, 30)
            self.assertFalse(git_tracked)

    def test_defaults_on_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, ".continuity")
            os.makedirs(target)
            with open(os.path.join(target, "metadata.json"), "w", encoding="utf-8") as handle:
                handle.write("{not valid json")

            retention_days, git_tracked = read_metadata_defaults(target)
            self.assertEqual(retention_days, 60)
            self.assertTrue(git_tracked)


if __name__ == "__main__":
    unittest.main()
