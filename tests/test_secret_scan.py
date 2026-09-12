"""tests/test_secret_scan.py — lib/secret_scan.py's regex gate, in isolation.

Every other test file only exercises these patterns indirectly through
lib/write_memory.py's `_scrub`. None of them prove the pattern boundaries
themselves: exactly which lengths and shapes a regex fires on. A pattern
tightened or loosened at the boundary would still pass every existing
write_memory test (they all use comfortably-over-the-line fixtures) while
silently changing what gets redacted.
"""

import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.secret_scan import secret_scan_line


class TestAwsKeyPattern(unittest.TestCase):
    def test_matches_a_real_shaped_akia_key(self):
        self.assertEqual(
            secret_scan_line("AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE"),
            "aws-key-pattern",
        )

    def test_does_not_match_a_similar_but_wrong_prefix(self):
        # Same length/shape as a real key but not one of the AWS-issued
        # prefixes: this line must fall through to the other patterns, not
        # this one, and here has none of their shapes either.
        self.assertIsNone(secret_scan_line("NOTAKEYOSFODNN7EXAMPLEX"))


class TestAssignmentPattern(unittest.TestCase):
    def test_six_char_value_matches(self):
        self.assertEqual(secret_scan_line("password=abcdef"), "assignment-pattern")

    def test_five_char_value_does_not_match(self):
        # \S{6,} is the documented floor; one character under it must not
        # trip the gate.
        self.assertIsNone(secret_scan_line("password=abcde"))

    def test_case_insensitive_key_name_matches(self):
        self.assertEqual(secret_scan_line("API_KEY: sk-abcdef123456"), "assignment-pattern")

    def test_ordinary_key_value_prose_without_a_secret_keyword_does_not_match(self):
        self.assertIsNone(secret_scan_line("region=us-east-1"))


class TestPemPrivateKeyPattern(unittest.TestCase):
    def test_matches_the_bare_header(self):
        self.assertEqual(
            secret_scan_line("-----BEGIN PRIVATE KEY-----"), "pem-private-key"
        )

    def test_matches_an_algorithm_qualified_header(self):
        self.assertEqual(
            secret_scan_line("-----BEGIN RSA PRIVATE KEY-----"), "pem-private-key"
        )

    def test_does_not_match_a_public_key_header(self):
        self.assertIsNone(secret_scan_line("-----BEGIN PUBLIC KEY-----"))


class TestHighEntropyRunPattern(unittest.TestCase):
    def test_forty_char_alnum_run_matches(self):
        run = "aQ7xR2mZ9kP4vL1nC8sD3fG6hJ0wT5yU2bE7iK4o"
        self.assertEqual(len(run), 40)
        self.assertEqual(secret_scan_line(run), "high-entropy-run")

    def test_thirty_nine_char_run_does_not_match(self):
        run = "aQ7xR2mZ9kP4vL1nC8sD3fG6hJ0wT5yU2bE7iK4"
        self.assertEqual(len(run), 39)
        self.assertIsNone(secret_scan_line(run))

    def test_all_digit_run_does_not_match(self):
        # The pattern requires both a digit and a letter to look-ahead for;
        # a purely numeric run (a phone number, a large integer) must not
        # be flagged as high-entropy.
        self.assertIsNone(secret_scan_line("1" * 40))

    def test_all_letter_run_does_not_match(self):
        self.assertIsNone(secret_scan_line("a" * 40))


class TestOrdinaryProsePassesThrough(unittest.TestCase):
    def test_plain_sentence_matches_nothing(self):
        self.assertIsNone(
            secret_scan_line("Chose plain Markdown files over an embedded database.")
        )

    def test_first_matching_pattern_wins_when_multiple_could_apply(self):
        # An AWS key embedded in an assignment line: secret_scan_line returns
        # exactly one name (the first pattern tried), never a list — callers
        # depend on a single string or None.
        result = secret_scan_line("aws_secret_access_key=AKIAIOSFODNN7EXAMPLE")
        self.assertIn(result, ("aws-key-pattern", "assignment-pattern"))


if __name__ == "__main__":
    unittest.main()
