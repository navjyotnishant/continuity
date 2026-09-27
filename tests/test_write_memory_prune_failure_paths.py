"""tests/test_write_memory_prune_failure_paths.py — T032's fail-open contract.

Covers the parts of the ticket's acceptance list that neither
`tests/test_write_memory_basic.py`, `tests/test_write_memory_retention_wiring.py`,
nor `tests/test_retention.py` pin down:

  7.  a `retention_prune` exception does not raise out of `write_memory` and
      does not cost the caller the handoff it already produced
  8.  that exception is logged to `errors.log` under the `retention` operation
  9.  `retention_prune` succeeds against a store with no sessions at all
  10. `retention_prune` succeeds when nothing in the store is stale
  11. a single file-deletion permission error during pruning does not crash
      the sweep
  12. a partial prune failure (one deletion fails, another succeeds) removes
      what it can and leaves the rest, without raising
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.retention import retention_prune
from lib.write_memory import write_memory

DEFAULT_RETENTION_DAYS = 60


def stage(project_root, kind, body, suffix="20260912T140501Z-4242"):
    path = os.path.join(
        project_root, ".continuity", ".staged", "{}-{}.md".format(kind, suffix)
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def session_filename(age_days):
    ts = (datetime.now(timezone.utc) - timedelta(days=age_days)).strftime(
        "%Y%m%dT%H%M%SZ"
    )
    return "{}-4242.md".format(ts)


def session_body():
    return "```\ncaptured_at: x\ntrigger: file-change\n```\n\nOld.\n"


class TestPruneErrorDoesNotCostTheCallerTheHandoff(unittest.TestCase):
    def test_a_retention_prune_exception_does_not_raise_and_handoff_still_returns(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Kept despite the prune failing\n\nBody.\n")

            with mock.patch(
                "lib.write_memory.retention_prune", side_effect=RuntimeError("boom")
            ):
                handoff_path = write_memory(tmp, "file-change")

            self.assertIsNotNone(
                handoff_path, "a prune failure must not cost the caller the handoff"
            )
            self.assertTrue(os.path.exists(handoff_path))
            store = os.path.join(tmp, ".continuity")
            self.assertIn("Kept despite the prune failing", read(os.path.join(store, "decisions.md")))

    def test_the_prune_exception_is_logged_under_the_retention_operation(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Logged\n\nBody.\n")
            store = os.path.join(tmp, ".continuity")

            with mock.patch(
                "lib.write_memory.retention_prune", side_effect=RuntimeError("boom")
            ):
                write_memory(tmp, "file-change")

            errors = read(os.path.join(store, "errors.log"))
            self.assertIn("retention", errors)
            self.assertIn("write-failed", errors)
            self.assertIn("RuntimeError", errors)


class TestPruneSucceedsWithNothingToDo(unittest.TestCase):
    def test_prune_succeeds_against_a_store_with_no_sessions_directory_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)

            try:
                retention_prune(store)
            except Exception as error:  # noqa: BLE001
                self.fail("retention_prune raised with no sessions dir: {}".format(error))

            self.assertFalse(os.path.exists(os.path.join(store, "sessions")))

    def test_prune_succeeds_against_an_empty_sessions_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(os.path.join(store, "sessions"))

            try:
                retention_prune(store)
            except Exception as error:  # noqa: BLE001
                self.fail("retention_prune raised on an empty sessions dir: {}".format(error))

            self.assertEqual(os.listdir(os.path.join(store, "sessions")), [])

    def test_prune_leaves_everything_when_nothing_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            fresh = os.path.join(store, "sessions", session_filename(1))
            os.makedirs(os.path.dirname(fresh))
            with open(fresh, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(session_body())

            try:
                retention_prune(store)
            except Exception as error:  # noqa: BLE001
                self.fail("retention_prune raised with nothing stale: {}".format(error))

            self.assertTrue(os.path.exists(fresh))


class TestPermissionErrorsDuringDeletionDoNotCrashThePrune(unittest.TestCase):
    def test_a_single_unlink_permission_error_does_not_crash_the_sweep(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            stale = os.path.join(store, "sessions", session_filename(DEFAULT_RETENTION_DAYS + 5))
            os.makedirs(os.path.dirname(stale))
            with open(stale, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(session_body())

            with mock.patch(
                "lib.retention.os.unlink", side_effect=PermissionError("denied")
            ):
                try:
                    retention_prune(store)
                except Exception as error:  # noqa: BLE001
                    self.fail(
                        "retention_prune raised on a permission error: {}".format(error)
                    )

            # The sweep logged the failure rather than silently swallowing it.
            errors_log = os.path.join(store, "errors.log")
            self.assertTrue(os.path.exists(errors_log))
            self.assertIn("retention", read(errors_log))

    def test_partial_prune_failure_removes_what_it_can(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            sessions = os.path.join(store, "sessions")
            os.makedirs(sessions)
            fails_name = session_filename(DEFAULT_RETENTION_DAYS + 5)
            succeeds_name = session_filename(DEFAULT_RETENTION_DAYS + 6)
            for name in (fails_name, succeeds_name):
                with open(
                    os.path.join(sessions, name), "w", encoding="utf-8", newline="\n"
                ) as handle:
                    handle.write(session_body())

            real_unlink = os.unlink

            def flaky_unlink(path, *args, **kwargs):
                if os.path.basename(path) == fails_name:
                    raise PermissionError("denied")
                return real_unlink(path, *args, **kwargs)

            with mock.patch("lib.retention.os.unlink", side_effect=flaky_unlink):
                try:
                    retention_prune(store)
                except Exception as error:  # noqa: BLE001
                    self.fail(
                        "a partial prune failure must not raise: {}".format(error)
                    )

            self.assertTrue(
                os.path.exists(os.path.join(sessions, fails_name)),
                "the file whose deletion failed must remain",
            )
            self.assertFalse(
                os.path.exists(os.path.join(sessions, succeeds_name)),
                "the file whose deletion succeeded must still be gone",
            )


if __name__ == "__main__":
    unittest.main()
