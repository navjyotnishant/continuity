"""tests/test_layout.py — the plugin lives in plugins/continuity/ (CONTINUI-59).

Codex ignores a marketplace plugin whose source is the repo root, so the
marketplace at the repo root points at this subfolder.
"""

import json
import os
import unittest

PLUGIN_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(PLUGIN_ROOT, "..", ".."))


class TestLayout(unittest.TestCase):
    def test_marketplace_points_at_the_plugin_subfolder(self):
        with open(os.path.join(PROJECT_ROOT, ".claude-plugin", "marketplace.json"), encoding="utf-8") as handle:
            marketplace = json.load(handle)
        entry = [p for p in marketplace["plugins"] if p["name"] == "continuity"][0]
        self.assertEqual(entry["source"], "./plugins/continuity")
        target = os.path.normpath(os.path.join(PROJECT_ROOT, entry["source"]))
        self.assertEqual(target, PLUGIN_ROOT)

    def test_plugin_root_has_its_manifest_and_hooks(self):
        for rel in (".claude-plugin/plugin.json", "hooks/hooks.json", "lib/write_memory.py"):
            self.assertTrue(os.path.isfile(os.path.join(PLUGIN_ROOT, rel)), rel)

    def test_no_symlinks_in_the_plugin(self):
        # Codex installs symlinked entries as nothing (verification.md, V3).
        for directory, dirs, files in os.walk(PLUGIN_ROOT):
            for name in dirs + files:
                self.assertFalse(os.path.islink(os.path.join(directory, name)), os.path.join(directory, name))


if __name__ == "__main__":
    unittest.main()
