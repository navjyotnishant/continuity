"""tests/test_session_startup_overhead.py — CONTINUI-12 (US2: Never notice
Continuity is running).

spec.md US2: loading prior context at SessionStart must not be a wait the
user notices. select_context.py already bounds the injected text (MAX_BYTES
/ MAX_LINES, covered in test_select_context.py); this covers the other half
of "imperceptible" — wall-clock time. The hook is driven exactly as Claude
Code drives it (a JSON payload on stdin, a real subprocess) against a
populated store, and against an oversized one, so the bound holds even when
select_context has real trimming work to do.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

SESSION_START_HOOK = os.path.join(REPO_ROOT, "hooks", "session-start.py")

# Generous enough to absorb interpreter startup and slow CI runners; tight
# enough that anything a user would actually perceive as a pause fails it.
IMPERCEPTIBLE_SECONDS = 1.0


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def entry(kind, title, index):
    return (
        "## {}: {} #{}\n\n```\ncaptured_at: 2026-09-{:02d}T10:00:00Z\n"
        "category: {}\n```\n\nBody text for entry {}.\n"
    ).format(kind.capitalize(), title, index, index % 28 + 1, kind, index)


def build_populated_store(root, entry_count):
    store = os.path.join(root, ".continuity")
    write(
        os.path.join(store, "state.md"),
        "# Project State\n\n```\nupdated_at: 2026-09-12T09:00:00Z\n```\n\nCurrent state.\n",
    )
    for kind in ("decision", "task", "learning"):
        entries = [entry(kind, "Entry", index) for index in range(entry_count)]
        write(os.path.join(store, kind + "s.md"), "\n".join(entries))
    write(
        os.path.join(store, "sessions", "20260912T140501Z-1.md"),
        "```\ncaptured_at: 2026-09-12T14:05:01Z\ntrigger: session-end\n```\n\nHandoff body.\n",
    )
    return store


def run_hook(cwd, timeout=30):
    started = time.monotonic()
    result = subprocess.run(
        [sys.executable, SESSION_START_HOOK],
        input=json.dumps({"session_id": "s", "cwd": cwd}),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    return result, time.monotonic() - started


class TestSessionStartupOverheadWithMemoryPresent(unittest.TestCase):
    def test_populated_store_loads_within_the_imperceptible_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            build_populated_store(tmp, entry_count=20)
            result, elapsed = run_hook(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("additionalContext", payload["hookSpecificOutput"])
            self.assertLess(elapsed, IMPERCEPTIBLE_SECONDS)

    def test_oversized_store_still_loads_within_the_imperceptible_bound(self):
        # select_context.py has real trimming work to do here (MAX_BYTES /
        # MAX_LINES), which is exactly where overhead would show up first.
        with tempfile.TemporaryDirectory() as tmp:
            build_populated_store(tmp, entry_count=200)
            result, elapsed = run_hook(tmp)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertLess(elapsed, IMPERCEPTIBLE_SECONDS)

    def test_overhead_versus_no_store_at_all_is_small(self):
        # The real acceptance criterion: a session with memory must not feel
        # meaningfully slower to start than one with none at all.
        with tempfile.TemporaryDirectory() as empty_project:
            _, baseline = run_hook(empty_project)

        with tempfile.TemporaryDirectory() as tmp:
            build_populated_store(tmp, entry_count=20)
            _, with_memory = run_hook(tmp)

        self.assertLess(with_memory - baseline, IMPERCEPTIBLE_SECONDS)


if __name__ == "__main__":
    unittest.main()
