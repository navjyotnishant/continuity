"""tests/test_agents.py — lib/agents.py: one module knows how coding agents differ."""

import json
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib import agents

FIXTURES = os.path.join(REPO_ROOT, "tests", "fixtures", "agents")


def fixture(agent, name):
    with open(os.path.join(FIXTURES, agent, name + ".json"), encoding="utf-8") as handle:
        data = json.load(handle)
    return data["payload"], data.get("_env", {})


class TestDetectAgent(unittest.TestCase):
    def test_pascal_case_event_is_claude(self):
        self.assertEqual(agents.detect_agent({"hook_event_name": "SessionStart"}), agents.CLAUDE)

    def test_camel_case_event_is_cursor(self):
        self.assertEqual(agents.detect_agent({"hook_event_name": "sessionStart"}), agents.CURSOR)

    def test_apply_patch_is_codex(self):
        payload = {"hook_event_name": "PostToolUse", "tool_name": "apply_patch"}
        self.assertEqual(agents.detect_agent(payload), agents.CODEX)

    def test_empty_payload_is_claude(self):
        self.assertEqual(agents.detect_agent({}), agents.CLAUDE)

    def test_recorded_payloads_detect_as_their_agent(self):
        for agent, names in (
            (agents.CLAUDE, ["SessionStart", "PostToolUse-Edit", "PostToolUse-Bash", "SessionEnd"]),
            (agents.CODEX, ["PostToolUse-apply_patch"]),
            (agents.CURSOR, ["sessionStart", "afterFileEdit", "afterShellExecution", "sessionEnd"]),
        ):
            for name in names:
                payload, _ = fixture(agent, name)
                self.assertEqual(agents.detect_agent(payload), agent, name)


class TestClaudeCodeInsideCursorTerminal(unittest.TestCase):
    """Review Focus 1: Cursor's env vars must not reroute Claude Code's own hooks."""

    def test_claude_payload_with_cursor_env_is_unchanged(self):
        payload = {"hook_event_name": "SessionStart", "cwd": "/work/repo"}
        env = {"CURSOR_VERSION": "2.0", "CURSOR_PROJECT_DIR": "/elsewhere"}
        self.assertEqual(agents.detect_agent(payload), agents.CLAUDE)
        self.assertEqual(agents.normalize(payload, env), [payload])


class TestNormalizeClaude(unittest.TestCase):
    def test_claude_payload_passes_through_untouched(self):
        payload, env = fixture(agents.CLAUDE, "PostToolUse-Edit")
        self.assertEqual(agents.normalize(payload, env), [payload])


class TestNormalizeCursor(unittest.TestCase):
    def test_session_start_takes_root_from_cursor_project_dir(self):
        out = agents.normalize({"hook_event_name": "sessionStart"}, {"CURSOR_PROJECT_DIR": "/work/repo"})
        self.assertEqual(out, [{"cwd": "/work/repo", "hook_event_name": "SessionStart"}])

    def test_root_falls_back_to_first_workspace_root(self):
        # Review Focus 4
        payload = {"hook_event_name": "sessionStart", "workspace_roots": ["/work/a", "/work/b"]}
        self.assertEqual(agents.normalize(payload, {})[0]["cwd"], "/work/a")

    def test_no_root_anywhere_leaves_cwd_none(self):
        # Review Focus 4: the hook then falls back to its own process cwd.
        self.assertIsNone(agents.normalize({"hook_event_name": "sessionStart"}, {})[0]["cwd"])

    def test_after_file_edit_becomes_multi_edit(self):
        payload = {
            "hook_event_name": "afterFileEdit",
            "file_path": "/work/repo/a.py",
            "edits": [{"old_string": "a", "new_string": "b"}],
        }
        out = agents.normalize(payload, {"CURSOR_PROJECT_DIR": "/work/repo"})
        self.assertEqual(
            out,
            [{
                "cwd": "/work/repo",
                "hook_event_name": "PostToolUse",
                "tool_name": "MultiEdit",
                "tool_input": {"file_path": "/work/repo/a.py", "edits": [{"old_string": "a", "new_string": "b"}]},
            }],
        )

    def test_after_shell_execution_becomes_bash(self):
        payload = {"hook_event_name": "afterShellExecution", "command": "git commit -m x"}
        out = agents.normalize(payload, {"CURSOR_PROJECT_DIR": "/work/repo"})
        self.assertEqual(out[0]["tool_name"], "Bash")
        self.assertEqual(out[0]["tool_input"], {"command": "git commit -m x"})

    def test_session_end_becomes_session_end(self):
        out = agents.normalize({"hook_event_name": "sessionEnd"}, {"CURSOR_PROJECT_DIR": "/r"})
        self.assertEqual(out, [{"cwd": "/r", "hook_event_name": "SessionEnd"}])

    def test_unmapped_event_is_a_no_op(self):
        # Review Focus 5
        self.assertEqual(agents.normalize({"hook_event_name": "stop"}, {"CURSOR_PROJECT_DIR": "/r"}), [])

    def test_recorded_cursor_payloads_all_normalize(self):
        for name in ("sessionStart", "afterFileEdit", "afterShellExecution", "sessionEnd"):
            payload, env = fixture(agents.CURSOR, name)
            out = agents.normalize(payload, env)
            self.assertEqual(len(out), 1, name)
            self.assertTrue(out[0]["cwd"], name)


class TestNormalizeCodexPatch(unittest.TestCase):
    PATCH = (
        "*** Begin Patch\n"
        "*** Update File: src/a.py\n"
        "@@\n-x = 1\n+x = 2\n"
        "*** Add File: /other/repo/b.py\n"
        "+print('hi')\n"
        "*** End Patch\n"
    )

    def payload(self, command):
        return {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "cwd": "/work/repo", "tool_input": {"command": command}}

    def test_each_patched_file_becomes_an_edit(self):
        # Review Focus 2
        out = agents.normalize(self.payload(self.PATCH), {})
        self.assertEqual(
            [p["tool_input"]["file_path"] for p in out], ["/work/repo/src/a.py", "/other/repo/b.py"]
        )
        self.assertTrue(all(p["tool_name"] == "Edit" and p["cwd"] == "/work/repo" for p in out))

    def test_command_given_as_list_is_joined(self):
        out = agents.normalize(self.payload(["apply_patch", self.PATCH]), {})
        self.assertEqual(len(out), 2)

    def test_whitespace_only_patch_is_a_no_op(self):
        # Review Focus 3
        patch = "*** Begin Patch\n*** Update File: a.py\n@@\n-x = 1\n+x  =  1\n*** End Patch\n"
        self.assertEqual(agents.normalize(self.payload(patch), {}), [])

    def test_patch_without_headers_falls_back_to_cwd_capture(self):
        out = agents.normalize(self.payload("not a patch"), {})
        self.assertEqual(out, [dict(self.payload("not a patch"), tool_name="Edit", tool_input={})])

    def test_recorded_codex_patch_names_its_file(self):
        payload, env = fixture(agents.CODEX, "PostToolUse-apply_patch")
        out = agents.normalize(payload, env)
        self.assertTrue(out)
        self.assertTrue(all(os.path.isabs(p["tool_input"].get("file_path", "/")) for p in out))


class TestPatchPaths(unittest.TestCase):
    def test_move_to_and_delete_are_included_once(self):
        patch = "*** Update File: a.py\n*** Move to: b.py\n*** Delete File: a.py\n"
        self.assertEqual(agents.patch_paths(patch, "/r"), ["/r/a.py", "/r/b.py"])

    def test_relative_path_without_cwd_is_dropped(self):
        self.assertEqual(agents.patch_paths("*** Add File: a.py\n", None), [])


class TestFormatContext(unittest.TestCase):
    def test_claude_output_is_byte_identical_to_v012(self):
        expected = json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "x\n"}})
        self.assertEqual(agents.format_context(agents.CLAUDE, "SessionStart", "x\n"), expected)

    def test_codex_uses_the_claude_shape(self):
        self.assertEqual(
            agents.format_context(agents.CODEX, "SessionStart", "x"),
            agents.format_context(agents.CLAUDE, "SessionStart", "x"),
        )

    def test_cursor_uses_additional_context(self):
        self.assertEqual(json.loads(agents.format_context(agents.CURSOR, "SessionStart", "x")), {"additional_context": "x"})


if __name__ == "__main__":
    unittest.main()
