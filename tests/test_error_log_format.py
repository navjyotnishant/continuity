"""tests/test_error_log_format.py — lib/common.py's errors.log contract.

contracts/file-format-contract.md's Failure Log Entry: one pipe-delimited
line per failure, `<ISO-8601 UTC timestamp> | <operation> | <failure-kind> |
<detail>`, with every field scrubbed to a single line. FR-012 (fail open):
if even the log write itself fails, that failure is swallowed silently
rather than raised or re-logged.
"""

import os
import re
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.common import continuity_log

TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class TestPipeDelimitedFormat(unittest.TestCase):
    def test_entry_has_exactly_four_pipe_delimited_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, ".continuity")
            continuity_log(target, "write-memory", "write-failed", "OSError")

            with open(os.path.join(target, "errors.log"), encoding="utf-8") as handle:
                line = handle.readline()

            fields = [part.strip() for part in line.rstrip("\n").split("|")]
            self.assertEqual(len(fields), 4)
            self.assertEqual(fields[1], "write-memory")
            self.assertEqual(fields[2], "write-failed")
            self.assertEqual(fields[3], "OSError")


class TestTimestampFormat(unittest.TestCase):
    def test_timestamp_is_iso8601_utc(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, ".continuity")
            continuity_log(target, "op", "kind", "detail")

            with open(os.path.join(target, "errors.log"), encoding="utf-8") as handle:
                line = handle.readline()

            timestamp = line.split("|")[0].strip()
            self.assertRegex(timestamp, TIMESTAMP_RE)


class TestDetailFieldScrubbing(unittest.TestCase):
    def test_pipes_and_newlines_in_detail_do_not_break_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, ".continuity")
            continuity_log(
                target, "secret-scan-block", "secret-blocked", "a | b\nc\nd | e"
            )

            with open(os.path.join(target, "errors.log"), encoding="utf-8") as handle:
                contents = handle.read()

            lines = contents.splitlines()
            self.assertEqual(len(lines), 1, "a scrubbed detail must not add newlines")
            fields = [part.strip() for part in lines[0].split("|")]
            self.assertEqual(len(fields), 4)
            self.assertNotIn("\n", fields[3])

    def test_pipes_and_newlines_in_operation_and_failure_kind_are_scrubbed_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, ".continuity")
            continuity_log(target, "op|erat\nion", "kind|with\nnewline", "detail")

            with open(os.path.join(target, "errors.log"), encoding="utf-8") as handle:
                contents = handle.read()

            self.assertEqual(len(contents.splitlines()), 1)
            fields = [part.strip() for part in contents.rstrip("\n").split("|")]
            self.assertEqual(len(fields), 4)


class TestLogWriteFailureIsSwallowed(unittest.TestCase):
    def test_unwritable_errors_log_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, ".continuity")
            with mock.patch("builtins.open", side_effect=OSError("disk full")):
                try:
                    result = continuity_log(target, "op", "kind", "detail")
                except Exception as error:  # pragma: no cover - failure path
                    self.fail("continuity_log raised: {!r}".format(error))
            self.assertIsNone(result)

    def test_a_parent_that_cannot_become_a_directory_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A plain file sitting where `.continuity/` needs to be a
            # directory makes os.makedirs fail with OSError/NotADirectoryError.
            blocker = os.path.join(tmp, "blocked")
            with open(blocker, "w", encoding="utf-8") as handle:
                handle.write("not a directory")
            target = os.path.join(blocker, ".continuity")

            try:
                result = continuity_log(target, "op", "kind", "detail")
            except Exception as error:  # pragma: no cover - failure path
                self.fail("continuity_log raised: {!r}".format(error))
            self.assertIsNone(result)
            self.assertFalse(os.path.isdir(target))


if __name__ == "__main__":
    unittest.main()
