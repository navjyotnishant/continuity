"""tests/test_select_context.py — the SessionStart read path (T013).

Covers FR-005 (bounded context), FR-007 (no history yet is not an error), and
contracts/hook-io-contract.md's SessionStart output shape, including the
hook script itself driven the way Claude Code drives it: a JSON payload on
stdin.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.select_context import LABEL, MAX_BYTES, MAX_LINES, select_context

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


def build_store(root, entry_count=1):
    """Build a fixture `.continuity/` store. entry_count scales its size."""
    store = os.path.join(root, ".continuity")

    write(
        os.path.join(store, "state.md"),
        "# Project State\n\n```\nupdated_at: 2026-09-12T09:00:00Z\n```\n\n"
        "Continuity's read path is built; the write path is next.\n\n"
        "## Constraints\n\n- Python 3.9+ stdlib only, no third-party imports.\n"
        "- Every hook fails open.\n",
    )

    decisions = [
        entry(
            "decision",
            "Store memory as plain Markdown under .continuity/ #%d" % index,
            "2026-09-%02dT10:00:00Z" % (index % 28 + 1),
            "Chosen over an embedded database so the store stays diffable.\n",
        )
        for index in range(entry_count)
    ]
    write(os.path.join(store, "decisions.md"), "\n".join(decisions))

    tasks = [
        entry(
            "task",
            "Finished long ago #%d" % index,
            "2026-09-01T10:00:00Z",
            "Already complete.\n",
            status="done",
        )
        for index in range(entry_count)
    ]
    tasks.append(
        entry(
            "task",
            "Wire the PostToolUse trigger",
            "2026-09-12T11:00:00Z",
            "Blocked on the detachment idiom.\n",
            status="blocked",
        )
    )
    write(os.path.join(store, "tasks.md"), "\n".join(tasks))

    learnings = [
        entry(
            "learning",
            "os.replace() is atomic on Windows too #%d" % index,
            "2026-09-%02dT12:00:00Z" % (index % 28 + 1),
            "Same filesystem only.\n",
        )
        for index in range(entry_count)
    ]
    write(os.path.join(store, "learnings.md"), "\n".join(learnings))

    write(
        os.path.join(store, "sessions", "20260912T140501Z-48213.md"),
        "```\ncaptured_at: 2026-09-12T14:05:01Z\ntrigger: session-end\n```\n\n"
        "Left off mid-way through the selection budget.\n",
    )
    return store


class TestSelectContext(unittest.TestCase):
    def test_includes_every_section_of_the_contract_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            context = select_context(build_store(tmp))

            self.assertTrue(context.startswith(LABEL))
            for heading in (
                "## State (as of 2026-09-12T09:00:00Z)",
                "## Constraints",
                "## Active tasks",
                "## Recent decisions",
                "## Recent learnings",
                "## Last handoff (2026-09-12T14:05:01Z)",
            ):
                self.assertIn(heading, context)

            # The acceptance criteria name these four by name.
            self.assertIn("Python 3.9+ stdlib only", context)
            self.assertIn("Wire the PostToolUse trigger", context)
            self.assertIn("Store memory as plain Markdown", context)
            self.assertIn("Left off mid-way", context)

    def test_stays_within_budget_on_an_oversized_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp, entry_count=200)
            context = select_context(store)

            self.assertLessEqual(len(context.splitlines()), MAX_LINES)
            self.assertLessEqual(len(context.encode("utf-8")), MAX_BYTES)
            # Bounding must not cost the sections US1 is graded on.
            self.assertIn("## Active tasks", context)
            self.assertIn("## Last handoff", context)
            self.assertIn("Wire the PostToolUse trigger", context)

    def test_unfinished_tasks_outrank_done_ones(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp, entry_count=40)
            context = select_context(store)

            # The one blocked task is older than nothing and newer than
            # nothing here — status, not recency, is what must put it first.
            self.assertLess(
                context.index("Wire the PostToolUse trigger"),
                context.index("Finished long ago"),
            )

    def test_absent_store_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(select_context(os.path.join(tmp, ".continuity")), "")

    def test_empty_store_is_empty_not_an_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(store)
            self.assertEqual(select_context(store), "")

    def test_malformed_entry_is_skipped_without_hiding_its_siblings(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp)
            write(
                os.path.join(store, "decisions.md"),
                "## Decision: missing its captured_at\n\n```\ncategory: decision\n```\n\n"
                "Should be skipped.\n\n"
                + entry(
                    "decision",
                    "Valid sibling",
                    "2026-09-10T10:00:00Z",
                    "Should still load.\n",
                ),
            )
            context = select_context(store)

            self.assertIn("Valid sibling", context)
            self.assertNotIn("missing its captured_at", context)

    def test_state_without_updated_at_is_treated_as_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp)
            write(os.path.join(store, "state.md"), "# Project State\n\nNo metadata.\n")
            context = select_context(store)

            self.assertNotIn("## State", context)
            self.assertIn("## Recent decisions", context)


class TestSessionStartHook(unittest.TestCase):
    def run_hook(self, cwd):
        return subprocess.run(
            [sys.executable, SESSION_START_HOOK],
            input=json.dumps({"session_id": "test-session", "cwd": cwd}),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )

    def test_emits_the_labeled_block_for_a_populated_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_store(tmp)
            result = self.run_hook(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(
                payload["hookSpecificOutput"]["hookEventName"], "SessionStart"
            )
            self.assertIn(LABEL, payload["hookSpecificOutput"]["additionalContext"])

    def test_omits_additional_context_when_there_is_no_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_hook(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(
                payload, {"hookSpecificOutput": {"hookEventName": "SessionStart"}}
            )
            self.assertFalse(os.path.exists(os.path.join(tmp, ".continuity")))

    def test_unsupported_newer_schema_injects_nothing_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = build_store(tmp)
            write(
                os.path.join(store, "metadata.json"),
                json.dumps({"schema_version": "9.0", "plugin_version": "9.0.0"}) + "\n",
            )
            decisions_path = os.path.join(store, "decisions.md")
            with open(decisions_path, encoding="utf-8") as handle:
                before = handle.read()

            result = self.run_hook(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertNotIn("additionalContext", payload["hookSpecificOutput"])
            with open(decisions_path, encoding="utf-8") as handle:
                self.assertEqual(handle.read(), before)
            with open(os.path.join(store, "errors.log"), encoding="utf-8") as handle:
                self.assertIn("unsupported-schema", handle.read())


if __name__ == "__main__":
    unittest.main()
