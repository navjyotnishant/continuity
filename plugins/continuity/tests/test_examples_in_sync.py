"""tests/test_examples_in_sync.py — docs/examples/store/ is what the writer produces.

The committed example store is generated from docs/examples/staged-notes/ by the
real writer (tests/example_store.py). If the writer changes and the example does
not, this fails and says how to regenerate it.
"""

import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from tests import example_store  # noqa: E402

REGENERATE = "python3 plugins/continuity/tests/example_store.py --write"


@unittest.skipUnless(os.path.isdir(example_store.NOTES), "docs/examples is not present in this checkout")
class TestExamplesInSync(unittest.TestCase):
    def committed(self):
        found = {}
        for folder, _, names in os.walk(example_store.STORE):
            for name in names:
                path = os.path.join(folder, name)
                with open(path, encoding="utf-8") as handle:
                    found[os.path.relpath(path, example_store.STORE).replace(os.sep, "/")] = handle.read()
        return found

    def test_committed_store_matches_what_the_writer_produces(self):
        built = example_store.build()
        committed = self.committed()
        self.assertEqual(sorted(committed), sorted(built), "file set differs; run: " + REGENERATE)
        for path, text in built.items():
            self.assertEqual(committed[path], text, path + " is stale; run: " + REGENERATE)

    def test_example_shows_each_behavior_it_documents(self):
        built = example_store.build()
        tasks = built["tasks.md"]
        self.assertEqual(tasks.count("## Task: Implement the lexer"), 1)
        self.assertIn("status: done", tasks)
        self.assertIn("updated_at:", tasks)
        self.assertIn("- No network access", built["state.md"])
        self.assertEqual(built["decisions.md"].count("## Decision:"), 2)
        self.assertEqual(len([p for p in built if p.startswith("sessions/")]), 2)


if __name__ == "__main__":
    unittest.main()
