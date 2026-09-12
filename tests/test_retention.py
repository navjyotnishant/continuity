"""tests/test_retention.py — lib/retention.py's `retention_prune` (T031).

Fabricates `sessions/` files, `errors.log` lines, and `.tmp.*` crash debris
at ages on both sides of their respective cutoffs (per
contracts/file-format-contract.md and data-model.md), then asserts
`retention_prune` deletes/trims only what is actually past its window —
durable files are never touched, regardless of age. Not yet implemented as
of this writing (T030) — this test is written against the contract and is
expected to fail until it lands.
"""

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.retention import retention_prune

DEFAULT_RETENTION_DAYS = 60
DURABLE_FILES = ("state.md", "decisions.md", "tasks.md", "learnings.md")


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)


def session_filename(age_days):
    ts = (datetime.now(timezone.utc) - timedelta(days=age_days)).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    return "{}-4242.md".format(ts)


def session_body(trigger="session-end"):
    return "```\ncaptured_at: {}\ntrigger: {}\n```\n\nBody.\n".format(
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), trigger
    )


def errors_log_line(age_days, detail):
    ts = (datetime.now(timezone.utc) - timedelta(days=age_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return "{} | write-memory | write-failed | {}\n".format(ts, detail)


def build_store(root, retention_days=None):
    store = os.path.join(root, ".continuity")
    if retention_days is not None:
        write(
            os.path.join(store, "metadata.json"),
            json.dumps(
                {
                    "schema_version": "1.0",
                    "plugin_version": "0.1.0",
                    "created_at": "2026-01-01T00:00:00Z",
                    "retention_days": retention_days,
                    "git_tracked": True,
                }
            ),
        )
    for name in DURABLE_FILES:
        write(os.path.join(store, name), "# Durable\n\nShould never be pruned.\n")
    return store


class TestSessionRetention(unittest.TestCase):
    def test_session_older_than_default_retention_is_deleted(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp)
            stale = os.path.join(store, "sessions", session_filename(DEFAULT_RETENTION_DAYS + 5))
            write(stale, session_body())

            retention_prune(store)

            self.assertFalse(os.path.exists(stale))

    def test_session_within_default_retention_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp)
            fresh = os.path.join(store, "sessions", session_filename(10))
            write(fresh, session_body())

            retention_prune(store)

            self.assertTrue(os.path.exists(fresh))

    def test_configured_retention_days_overrides_the_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp, retention_days=5)
            # Older than the configured 5-day window but well inside the
            # 60-day default — proves metadata.json's value governs, not a
            # hardcoded constant.
            aged_out = os.path.join(store, "sessions", session_filename(10))
            write(aged_out, session_body())

            retention_prune(store)

            self.assertFalse(os.path.exists(aged_out))

    def test_durable_files_are_never_deleted_regardless_of_age(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp)
            ancient = (datetime.now(timezone.utc) - timedelta(days=3650)).timestamp()
            paths = [os.path.join(store, name) for name in DURABLE_FILES]
            for path in paths:
                os.utime(path, (ancient, ancient))

            retention_prune(store)

            for path in paths:
                self.assertTrue(os.path.exists(path), path)
                with open(path, encoding="utf-8") as handle:
                    self.assertIn("Should never be pruned", handle.read())


class TestErrorsLogRetention(unittest.TestCase):
    def test_lines_older_than_retention_are_trimmed_from_the_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp)
            errors_log = os.path.join(store, "errors.log")
            write(
                errors_log,
                errors_log_line(DEFAULT_RETENTION_DAYS + 5, "old-entry")
                + errors_log_line(1, "recent-entry"),
            )

            retention_prune(store)

            with open(errors_log, encoding="utf-8") as handle:
                content = handle.read()
            self.assertNotIn("old-entry", content)
            self.assertIn("recent-entry", content)

    def test_errors_log_is_preserved_when_a_recent_line_survives(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp)
            errors_log = os.path.join(store, "errors.log")
            write(errors_log, errors_log_line(1, "recent-entry"))

            retention_prune(store)

            self.assertTrue(os.path.exists(errors_log))


class TestTmpOrphanSweep(unittest.TestCase):
    def test_tmp_orphan_older_than_an_hour_is_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp)
            orphan = os.path.join(store, "decisions.md.tmp.abc123")
            write(orphan, "half-written\n")
            old = (datetime.now(timezone.utc) - timedelta(hours=2)).timestamp()
            os.utime(orphan, (old, old))

            retention_prune(store)

            self.assertFalse(os.path.exists(orphan))

    def test_tmp_orphan_younger_than_an_hour_is_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp)
            fresh_orphan = os.path.join(store, "decisions.md.tmp.def456")
            write(fresh_orphan, "still being written\n")

            retention_prune(store)

            self.assertTrue(os.path.exists(fresh_orphan))


if __name__ == "__main__":
    unittest.main()
