#!/usr/bin/env python3
"""tests/run_tests.py — single entry point for the stdlib unittest suite.

Equivalent to `python3 -m unittest discover -s tests`, wrapped so CI and
CONTRIBUTING.md have one command to name. No third-party test framework
(see specs/001-continuity/plan.md's Testing Strategy).
"""

import sys
import unittest


def main():
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir="tests", top_level_dir=".")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
