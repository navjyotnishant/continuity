"""tests/test_hooks_json_registration.py — CONTINUI-12 (US2: Never notice
Continuity is running).

hooks/hooks.json is the plugin's event surface (T023). This proves the real
file registers all three lifecycle events with the right matcher and that
each hook command is portable (${CLAUDE_PLUGIN_ROOT}, not a baked-in path)
and dispatched via python3, so the plugin loads correctly regardless of
where it's installed.
"""

import json
import os
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HOOKS_JSON_PATH = os.path.join(REPO_ROOT, "hooks", "hooks.json")


def load_hooks():
    with open(HOOKS_JSON_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def first_command(hooks_config, event):
    return hooks_config["hooks"][event][0]["hooks"][0]["command"]


class TestHooksJsonEventRegistration(unittest.TestCase):
    def test_registers_session_start_event(self):
        hooks_config = load_hooks()
        self.assertIn("SessionStart", hooks_config["hooks"])

    def test_registers_post_tool_use_event_with_edit_write_multiedit_bash_matcher(self):
        hooks_config = load_hooks()
        self.assertIn("PostToolUse", hooks_config["hooks"])
        matcher = hooks_config["hooks"]["PostToolUse"][0]["matcher"]
        self.assertEqual(matcher, "Edit|Write|MultiEdit|Bash")

    def test_registers_session_end_event(self):
        hooks_config = load_hooks()
        self.assertIn("SessionEnd", hooks_config["hooks"])


class TestHookCommandsArePortable(unittest.TestCase):
    def test_session_start_command_uses_plugin_root_path(self):
        command = first_command(load_hooks(), "SessionStart")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", command)

    def test_session_start_command_starts_with_python3(self):
        command = first_command(load_hooks(), "SessionStart")
        self.assertTrue(command.startswith("python3"))

    def test_post_tool_use_command_uses_plugin_root_path(self):
        command = first_command(load_hooks(), "PostToolUse")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", command)

    def test_post_tool_use_command_starts_with_python3(self):
        command = first_command(load_hooks(), "PostToolUse")
        self.assertTrue(command.startswith("python3"))

    def test_session_end_command_uses_plugin_root_path(self):
        command = first_command(load_hooks(), "SessionEnd")
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", command)


if __name__ == "__main__":
    unittest.main()
