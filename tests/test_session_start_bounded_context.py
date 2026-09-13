"""tests/test_session_start_bounded_context.py — CONTINUI-12 (US2: Never
notice Continuity is running).

Acceptance criterion 3: when a new session starts, Continuity's bounded
context load must not be perceptible. `tests/test_select_context.py`
already proves `select_context()` itself stays within `MAX_LINES`/`MAX_BYTES`
on an oversized store; this proves the same bound holds end-to-end through
the real `hooks/session-start.py` process on the `additionalContext` a
session actually receives, so a future change that re-inflates the payload
between selection and hook output would be caught here even if it left
`select_context()` untouched.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.select_context import LABEL, MAX_BYTES, MAX_LINES

SESSION_START_HOOK = os.path.join(REPO_ROOT, "hooks", "session-start.py")


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def entry(kind, title, timestamp, body, status=None):
    fields = ["captured_at: " + timestamp, "category: " + kind]
    if status:
        fields.append("status: " + status)
    return "## {}: {}\n\n```\n{}\n```\n\n{}\n".format(
        kind.capitalize(), title, "\n".join(fields), body
    )


def build_oversized_store(root, entry_count=200):
    """A `.continuity/` store big enough that every section must be trimmed."""
    store = os.path.join(root, ".continuity")

    write(
        os.path.join(store, "state.md"),
        "# Project State\n\n```\nupdated_at: 2026-09-12T09:00:00Z\n```\n\n"
        + ("Long-lived project state. " * 50) + "\n",
    )
    write(
        os.path.join(store, "decisions.md"),
        "\n".join(
            entry(
                "decision",
                "Decision #%d" % index,
                "2026-09-%02dT10:00:00Z" % (index % 28 + 1),
                "Rationale text padded out. " * 10,
            )
            for index in range(entry_count)
        ),
    )
    write(
        os.path.join(store, "tasks.md"),
        "\n".join(
            entry(
                "task",
                "Task #%d" % index,
                "2026-09-01T10:00:00Z",
                "Some detail. " * 10,
                status="active",
            )
            for index in range(entry_count)
        ),
    )
    write(
        os.path.join(store, "learnings.md"),
        "\n".join(
            entry(
                "learning",
                "Learning #%d" % index,
                "2026-09-%02dT12:00:00Z" % (index % 28 + 1),
                "Detail padded out. " * 10,
            )
            for index in range(entry_count)
        ),
    )
    write(
        os.path.join(store, "sessions", "20260912T140501Z-48213.md"),
        "```\ncaptured_at: 2026-09-12T14:05:01Z\ntrigger: session-end\n```\n\n"
        + ("Handoff detail padded out. " * 10) + "\n",
    )
    return store


class TestBoundedContextLoadsAtSessionStart(unittest.TestCase):
    def run_hook(self, cwd):
        return subprocess.run(
            [sys.executable, SESSION_START_HOOK],
            input=json.dumps({"session_id": "test-session", "cwd": cwd}),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )

    def test_additional_context_stays_within_budget_on_an_oversized_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_oversized_store(tmp, entry_count=200)
            result = self.run_hook(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            context = payload["hookSpecificOutput"]["additionalContext"]

            self.assertTrue(context.startswith(LABEL))
            self.assertLessEqual(len(context.splitlines()), MAX_LINES)
            self.assertLessEqual(len(context.encode("utf-8")), MAX_BYTES)

    def test_bounded_context_still_carries_the_most_recent_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_oversized_store(tmp, entry_count=200)
            result = self.run_hook(tmp)

            payload = json.loads(result.stdout)
            context = payload["hookSpecificOutput"]["additionalContext"]
            self.assertIn("## Last handoff", context)


if __name__ == "__main__":
    unittest.main()
