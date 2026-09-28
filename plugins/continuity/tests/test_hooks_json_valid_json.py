"""tests/test_hooks_json_valid_json.py — CONTINUI-12 (US2: Never notice
Continuity is running).

T023's done-when clause requires `hooks/hooks.json` to parse as JSON (`python3
-m json.tool` or equivalent exits 0). `tests/test_hooks_json_registration.py`
already asserts on the *shape* of the parsed structure, but every one of its
tests relies on `json.load` succeeding as a side effect rather than proving
parseability is itself a checked property — a hand-edit that broke the JSON
syntax (a trailing comma, an unmatched brace) would fail loudly there, but
for the wrong stated reason. This is that property, isolated.
"""

import json
import os
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HOOKS_JSON_PATH = os.path.join(REPO_ROOT, "hooks", "hooks.json")


class TestHooksJsonIsValidJson(unittest.TestCase):
    def test_hooks_json_parses_without_error(self):
        with open(HOOKS_JSON_PATH, "r", encoding="utf-8") as handle:
            try:
                parsed = json.load(handle)
            except json.JSONDecodeError as error:
                self.fail("hooks/hooks.json is not valid JSON: {}".format(error))

        self.assertIsInstance(parsed, dict)

    def test_hooks_json_top_level_is_a_hooks_object(self):
        with open(HOOKS_JSON_PATH, "r", encoding="utf-8") as handle:
            parsed = json.load(handle)

        self.assertIn("hooks", parsed)
        self.assertIsInstance(parsed["hooks"], dict)


if __name__ == "__main__":
    unittest.main()
