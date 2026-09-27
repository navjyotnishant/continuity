"""tests/test_hooks_json_negative_cases.py — CONTINUI-12 (US2: Never notice
Continuity is running).

T023's done-when clause ("the JSON is valid ... and every `command` path
resolves under `${CLAUDE_PLUGIN_ROOT}`") is a validation contract, not just
a shape assertion. `test_hooks_json_registration.py` proves the *real* file
holds that contract; this proves a broken variant would be caught — a
hand-edit that drops an event, renames a script out from under the wiring,
loosens the PostToolUse matcher, hardcodes a path, or dispatches through
something other than `python3` must all fail the same checks that pass on
the real file today.

`validate_hooks_config()` below is test-only scaffolding (Continuity ships
no dedicated hooks.json schema validator) that encodes exactly the
properties `test_hooks_json_registration.py` already asserts individually,
so these negative cases and that file's positive ones are two views of one
contract.
"""

import copy
import json
import os
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
HOOKS_JSON_PATH = os.path.join(REPO_ROOT, "hooks", "hooks.json")

REQUIRED_EVENTS = ("SessionStart", "PostToolUse", "SessionEnd")
POST_TOOL_USE_MATCHER = "Edit|Write|MultiEdit|Bash"
PLUGIN_ROOT_TOKEN = "${CLAUDE_PLUGIN_ROOT}"


def load_hooks():
    with open(HOOKS_JSON_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_script_path(command):
    """Extract the filesystem path a `python3 "${CLAUDE_PLUGIN_ROOT}/..."` command
    names, relative to the repo root (which stands in for the plugin root at
    install time)."""
    marker = PLUGIN_ROOT_TOKEN + "/"
    start = command.find(marker)
    if start == -1:
        return None
    start += len(marker)
    end = command.find('"', start)
    relative = command[start:end] if end != -1 else command[start:]
    return os.path.join(REPO_ROOT, relative)


def validate_hooks_config(config):
    """Return a list of validation error strings; empty means valid.

    Encodes T023's done-when clause plus the shape
    `test_hooks_json_registration.py` checks against the real file.
    """
    errors = []
    hooks = config.get("hooks", {})

    for event in REQUIRED_EVENTS:
        if event not in hooks:
            errors.append("missing required event: {}".format(event))

    if "PostToolUse" in hooks:
        matcher = hooks["PostToolUse"][0].get("matcher")
        if matcher != POST_TOOL_USE_MATCHER:
            errors.append(
                "PostToolUse matcher must be {!r}, got {!r}".format(
                    POST_TOOL_USE_MATCHER, matcher
                )
            )

    for event in hooks:
        for binding in hooks[event]:
            for hook in binding.get("hooks", []):
                command = hook.get("command", "")
                if not command.startswith("python3"):
                    errors.append(
                        "{} command must start with python3: {!r}".format(event, command)
                    )
                if PLUGIN_ROOT_TOKEN not in command:
                    errors.append(
                        "{} command must use {}: {!r}".format(
                            event, PLUGIN_ROOT_TOKEN, command
                        )
                    )
                    continue
                script_path = resolve_script_path(command)
                if not script_path or not os.path.isfile(script_path):
                    errors.append(
                        "{} command names a script that does not exist: {!r}".format(
                            event, command
                        )
                    )

    return errors


class TestRealHooksJsonPassesValidation(unittest.TestCase):
    def test_real_file_has_no_validation_errors(self):
        self.assertEqual(validate_hooks_config(load_hooks()), [])


class TestMissingEventFailsValidation(unittest.TestCase):
    def test_dropping_session_end_fails_validation(self):
        config = copy.deepcopy(load_hooks())
        del config["hooks"]["SessionEnd"]

        errors = validate_hooks_config(config)

        self.assertIn("missing required event: SessionEnd", errors)


class TestMissingScriptFileFailsValidation(unittest.TestCase):
    def test_command_naming_a_nonexistent_script_fails_validation(self):
        config = copy.deepcopy(load_hooks())
        command = config["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        config["hooks"]["SessionStart"][0]["hooks"][0]["command"] = command.replace(
            "session-start.py", "session-start-does-not-exist.py"
        )

        errors = validate_hooks_config(config)

        self.assertTrue(
            any("does not exist" in error for error in errors),
            errors,
        )


class TestIncorrectPostToolUseMatcherFailsValidation(unittest.TestCase):
    def test_narrowed_matcher_fails_validation(self):
        config = copy.deepcopy(load_hooks())
        config["hooks"]["PostToolUse"][0]["matcher"] = "Edit|Write"

        errors = validate_hooks_config(config)

        self.assertTrue(
            any("PostToolUse matcher must be" in error for error in errors),
            errors,
        )

    def test_missing_matcher_key_fails_validation(self):
        config = copy.deepcopy(load_hooks())
        del config["hooks"]["PostToolUse"][0]["matcher"]

        errors = validate_hooks_config(config)

        self.assertTrue(
            any("PostToolUse matcher must be" in error for error in errors),
            errors,
        )


class TestCommandWithoutPluginRootPrefixFailsValidation(unittest.TestCase):
    def test_hardcoded_absolute_path_fails_validation(self):
        config = copy.deepcopy(load_hooks())
        config["hooks"]["SessionStart"][0]["hooks"][0]["command"] = (
            'python3 "/Users/someone/.claude/plugins/continuity/hooks/session-start.py"'
        )

        errors = validate_hooks_config(config)

        self.assertTrue(
            any(PLUGIN_ROOT_TOKEN in error for error in errors),
            errors,
        )


class TestCommandNotStartingWithPython3FailsValidation(unittest.TestCase):
    def test_sh_dispatch_fails_validation(self):
        config = copy.deepcopy(load_hooks())
        command = config["hooks"]["SessionEnd"][0]["hooks"][0]["command"]
        config["hooks"]["SessionEnd"][0]["hooks"][0]["command"] = command.replace(
            "python3 ", "sh "
        )

        errors = validate_hooks_config(config)

        self.assertTrue(
            any("must start with python3" in error for error in errors),
            errors,
        )

    def test_bare_python_without_the_3_suffix_fails_validation(self):
        config = copy.deepcopy(load_hooks())
        command = config["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
        config["hooks"]["PostToolUse"][0]["hooks"][0]["command"] = command.replace(
            "python3 ", "python "
        )

        errors = validate_hooks_config(config)

        self.assertTrue(
            any("must start with python3" in error for error in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
