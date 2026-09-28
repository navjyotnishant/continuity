"""tests/test_write_memory_secrets.py — the secret gate (research.md R5).

test_write_memory_basic.py already proves the AWS-key case end to end; this
file covers the rest of lib/secret_scan.py's patterns plus the whole-note
and pass-through edges lib/write_memory.py's `_scrub`/`_consolidate` add on
top of it.
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.write_memory import write_memory
from tests.test_write_memory_basic import read, sessions_files, stage


class TestSecretPatterns(unittest.TestCase):
    def test_assignment_pattern_line_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(
                tmp,
                "decision",
                "# Rotate the staging password\n\n"
                "Kept for reference only.\n"
                "password=Sup3rSecretValue\n"
                "Nothing else changed.\n",
            )

            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            decisions = read(os.path.join(store, "decisions.md"))
            self.assertIn("Kept for reference only", decisions)
            self.assertIn("Nothing else changed", decisions)
            self.assertNotIn("Sup3rSecretValue", decisions)

            errors = read(os.path.join(store, "errors.log"))
            self.assertIn("secret-blocked", errors)
            self.assertIn("assignment-pattern", errors)
            self.assertNotIn("Sup3rSecretValue", errors)

    def test_pem_private_key_header_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(
                tmp,
                "learning",
                "# Never paste a key into a note\n\n"
                "A teammate pasted one by mistake.\n"
                "-----BEGIN RSA PRIVATE KEY-----\n"
                "It was caught before it landed.\n",
            )

            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            learnings = read(os.path.join(store, "learnings.md"))
            self.assertIn("A teammate pasted one by mistake", learnings)
            self.assertIn("It was caught before it landed", learnings)
            self.assertNotIn("BEGIN RSA PRIVATE KEY", learnings)

            errors = read(os.path.join(store, "errors.log"))
            self.assertIn("secret-blocked", errors)
            self.assertIn("pem-private-key", errors)

    def test_high_entropy_run_is_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            entropy_run = "aQ7xR2mZ9kP4vL1nC8sD3fG6hJ0wT5yU2bE7iK4oM9"
            self.assertGreaterEqual(len(entropy_run), 40)
            stage(
                tmp,
                "task",
                "# Clean up the leftover debug output\n\n"
                "Found stray token in a log line.\n"
                + entropy_run
                + "\n"
                "Removed before commit.\n",
            )

            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            tasks = read(os.path.join(store, "tasks.md"))
            self.assertIn("Found stray token in a log line", tasks)
            self.assertIn("Removed before commit", tasks)
            self.assertNotIn(entropy_run, tasks)

            errors = read(os.path.join(store, "errors.log"))
            self.assertIn("secret-blocked", errors)
            self.assertIn("high-entropy-run", errors)
            self.assertNotIn(entropy_run, errors)

    def test_note_that_fails_on_every_line_is_dropped_whole_others_still_land(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(
                tmp,
                "decision",
                "AKIAIOSFODNN7EXAMPLE\n"
                "-----BEGIN PRIVATE KEY-----\n",
                suffix="20260912T140501Z-1",
            )
            stage(
                tmp,
                "decision",
                "# A clean second note\n\nThis one has no secrets in it.\n",
                suffix="20260912T140502Z-2",
            )

            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            decisions = read(os.path.join(store, "decisions.md"))
            self.assertIn("A clean second note", decisions)
            self.assertNotIn("AKIAIOSFODNN7EXAMPLE", decisions)
            self.assertNotIn("BEGIN PRIVATE KEY", decisions)
            # Only one entry made it through: the fully-secret note contributed nothing.
            self.assertEqual(decisions.count("## Decision:"), 1)

            errors = read(os.path.join(store, "errors.log"))
            self.assertIn("secret-blocked", errors)
            self.assertIn("staged note dropped whole", errors)

    def test_ordinary_prose_with_no_secrets_passes_through_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            body = (
                "# Use Markdown files instead of a database\n\n"
                "Keeps the store diffable, reviewable in a plain PR, and\n"
                "readable without any tooling at all.\n"
            )
            stage(tmp, "decision", body)

            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            decisions = read(os.path.join(store, "decisions.md"))
            self.assertIn("Keeps the store diffable, reviewable in a plain PR, and", decisions)
            self.assertIn("readable without any tooling at all.", decisions)
            self.assertFalse(
                os.path.exists(os.path.join(store, "errors.log")),
                "clean prose must not trigger any secret-scan log entry",
            )


if __name__ == "__main__":
    unittest.main()
