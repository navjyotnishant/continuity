"""tests/test_agent_packaging.py — one plugin, one manifest per coding agent."""

import ast
import json
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MANIFESTS = [".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json", "plugin.json"]
CURSOR_EVENTS = {"sessionStart", "sessionEnd", "afterFileEdit", "afterShellExecution", "stop"}


def load(rel):
    with open(os.path.join(REPO_ROOT, rel), encoding="utf-8") as handle:
        return json.load(handle)


class TestManifests(unittest.TestCase):
    def test_every_manifest_shares_name_and_version(self):
        pairs = {(load(m)["name"], load(m)["version"]) for m in MANIFESTS}
        self.assertEqual(len(pairs), 1, pairs)

    def test_no_manifest_names_the_auto_loaded_hooks_json(self):
        for m in MANIFESTS:
            hooks = load(m).get("hooks")
            self.assertNotIn(hooks, ("./hooks/hooks.json", "hooks/hooks.json"), m)

    def test_codex_manifest_points_at_skills(self):
        self.assertEqual(load(".codex-plugin/plugin.json")["skills"], "./skills/")
        self.assertTrue(os.path.isfile(os.path.join(REPO_ROOT, "skills", "continuity-checkpoint", "SKILL.md")))

    def test_cursor_manifest_points_at_cursor_hooks(self):
        self.assertEqual(load(".cursor-plugin/plugin.json")["hooks"], "./hooks/cursor-hooks.json")


class TestCursorHooks(unittest.TestCase):
    def test_only_cursor_event_names_and_existing_scripts(self):
        config = load("hooks/cursor-hooks.json")
        self.assertEqual(set(config["hooks"]), CURSOR_EVENTS)
        for entries in config["hooks"].values():
            for entry in entries:
                script = entry["command"].split("/hooks/")[1].rstrip('"')
                self.assertTrue(os.path.isfile(os.path.join(REPO_ROOT, "hooks", script)), script)


class TestAgentsModuleIsStdlibOnly(unittest.TestCase):
    def test_imports_are_standard_library(self):
        with open(os.path.join(REPO_ROOT, "lib", "agents.py"), encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        names = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        stdlib = getattr(sys, "stdlib_module_names", {"json", "os", "re"})
        self.assertTrue(names <= set(stdlib), names)


if __name__ == "__main__":
    unittest.main()
