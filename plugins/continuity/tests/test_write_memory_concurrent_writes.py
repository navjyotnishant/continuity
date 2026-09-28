"""tests/test_write_memory_concurrent_writes.py — CONTINUI-12 (US2: Never
notice Continuity is running).

`lib/lock.py`'s `os.mkdir()` lock (research.md R2) exists so that two
triggers landing back-to-back — a `PostToolUse` firing while a prior
`SessionEnd` writer is still consolidating, say — never interleave writes
into the same durable file. `tests/test_lock.py` proves the lock primitive
itself serializes contenders; this proves the thing that actually matters
end-to-end: two real `write_memory()` invocations racing against the same
`.continuity/` store never corrupt or duplicate a durable entry, and both
finish having done the right amount of work exactly once.
"""

import os
import sys
import tempfile
import threading
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.lock import lock_path
from lib.write_memory import write_memory


def stage(continuity_dir_path, kind, suffix, body):
    staged = os.path.join(continuity_dir_path, ".staged")
    os.makedirs(staged, exist_ok=True)
    path = os.path.join(staged, "{}-{}.md".format(kind, suffix))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)
    return path


class TestConcurrentWritesAreSerializedSafely(unittest.TestCase):
    def test_two_concurrent_write_memory_calls_do_not_corrupt_or_duplicate_entries(self):
        with tempfile.TemporaryDirectory() as project:
            continuity_dir_path = os.path.join(project, ".continuity")
            stage(continuity_dir_path, "decision", "20260912T140501Z-1", "# First\n\nFirst body.\n")
            stage(continuity_dir_path, "decision", "20260912T140502Z-2", "# Second\n\nSecond body.\n")

            results = [None, None]

            def call(index):
                results[index] = write_memory(project, "file-change")

            threads = [
                threading.Thread(target=call, args=(0,)),
                threading.Thread(target=call, args=(1,)),
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10.0)

            self.assertFalse(
                any(thread.is_alive() for thread in threads), "a writer thread hung"
            )

            decisions_path = os.path.join(continuity_dir_path, "decisions.md")
            with open(decisions_path, "r", encoding="utf-8") as handle:
                decisions_text = handle.read()

            # Each staged entry was consolidated exactly once — never dropped,
            # never duplicated by the two racing passes.
            self.assertEqual(decisions_text.count("Decision: First"), 1)
            self.assertEqual(decisions_text.count("Decision: Second"), 1)
            self.assertEqual(decisions_text.count("First body."), 1)
            self.assertEqual(decisions_text.count("Second body."), 1)

            # Every staged note was consumed by whichever pass actually
            # processed it; nothing is left orphaned in .staged/.
            staged_dir = os.path.join(continuity_dir_path, ".staged")
            self.assertEqual(
                [name for name in os.listdir(staged_dir) if name.endswith(".md")], []
            )

            # The lock is never left held after both passes finish.
            self.assertFalse(os.path.isdir(lock_path(continuity_dir_path)))

    def test_ten_concurrent_write_memory_calls_on_disjoint_notes_lose_nothing(self):
        with tempfile.TemporaryDirectory() as project:
            continuity_dir_path = os.path.join(project, ".continuity")
            note_count = 10
            for index in range(note_count):
                stage(
                    continuity_dir_path,
                    "learning",
                    "20260912T1405{:02d}Z-{}".format(index, index),
                    "# Learning {}\n\nBody {}.\n".format(index, index),
                )

            def call():
                write_memory(project, "file-change")

            threads = [threading.Thread(target=call) for _ in range(note_count)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=10.0)

            self.assertFalse(any(thread.is_alive() for thread in threads))

            learnings_path = os.path.join(continuity_dir_path, "learnings.md")
            with open(learnings_path, "r", encoding="utf-8") as handle:
                learnings_text = handle.read()

            # Ten independent writer threads, ten staged notes, ten entries —
            # not more (duplicated) and not fewer (lost mid-race).
            for index in range(note_count):
                self.assertEqual(
                    learnings_text.count("Learning {}".format(index)),
                    1,
                    "entry {} was lost or duplicated".format(index),
                )


if __name__ == "__main__":
    unittest.main()
