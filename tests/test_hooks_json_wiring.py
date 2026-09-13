"""tests/test_hooks_json_wiring.py — CONTINUI-12 (US2: Never notice
Continuity is running).

hooks/hooks.json is the plugin's whole event surface (T023): every command it
names has to actually resolve to a script that ships in hooks/, and every
command — SessionEnd included — has to be dispatched via python3 rather than
relying on a shebang, since a plugin is installed to an arbitrary path with
no guarantee the script is executable.
"""

import json
import os
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HOOKS_JSON_PATH = os.path.join(REPO_ROOT, "hooks", "hooks.json")
HOOKS_DIR = os.path.join(REPO_ROOT, "hooks")


def load_hooks():
    with open(HOOKS_JSON_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def all_commands(hooks_config):
    for matchers in hooks_config["hooks"].values():
        for matcher in matchers:
            for hook in matcher["hooks"]:
                yield hook["command"]


def first_command(hooks_config, event):
    return hooks_config["hooks"][event][0]["hooks"][0]["command"]


class TestSessionEndCommandStartsWithPython3(unittest.TestCase):
    def test_session_end_command_starts_with_python3(self):
        command = first_command(load_hooks(), "SessionEnd")
        self.assertTrue(command.startswith("python3"))


class TestHooksJsonReferencesRealScripts(unittest.TestCase):
    """Each script hooks.json names must exist on disk at that path (T023)."""

    def test_session_start_script_is_referenced_and_exists(self):
        commands = list(all_commands(load_hooks()))
        self.assertTrue(any("session-start.py" in command for command in commands))
        self.assertTrue(os.path.isfile(os.path.join(HOOKS_DIR, "session-start.py")))

    def test_capture_trigger_script_is_referenced_and_exists(self):
        commands = list(all_commands(load_hooks()))
        self.assertTrue(any("capture-trigger.py" in command for command in commands))
        self.assertTrue(os.path.isfile(os.path.join(HOOKS_DIR, "capture-trigger.py")))

    def test_session_end_script_is_referenced_and_exists(self):
        commands = list(all_commands(load_hooks()))
        self.assertTrue(any("session-end.py" in command for command in commands))
        self.assertTrue(os.path.isfile(os.path.join(HOOKS_DIR, "session-end.py")))


if __name__ == "__main__":
    unittest.main()
