# Multi-Agent Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Continuity installs from its GitHub marketplace in Claude Code, Codex and Cursor and recalls, captures and flushes the same way in all three.

**Architecture:** The three hook scripts stay shared. A new pure module, `lib/agents.py`, converts each agent's hook payload **into the Claude Code payload shape** the scripts already handle, and formats recall output for the calling agent. Cursor gets its own hook config file, and each agent gets its own manifest. Claude Desktop (Cowork) is documented as unsupported.

**Tech Stack:** Python 3.9+ standard library only; `unittest`; bash shell tests; `claude`, `codex` (0.141) and `cursor-agent` (2026.08) CLIs for the live runs.

**Spec:** [`specs/002-multi-agent/design.md`](./design.md) (commit `f0ac863`)  |  **Jira:** Epic CONTINUI-55, Stories CONTINUI-56..63

### Refinements to the spec (decided while planning)

1. **No `Event` type.** The spec sketched `read_event(...) -> Event(...)`. Instead,
   `agents.normalize()` returns Claude-shaped payloads, so `classify()`,
   `project_root_for()` and the whitespace rules run unchanged and stay covered by
   their existing tests. The spec's intent is kept: `lib/agents.py` is the only module
   that knows how agents differ.
2. **Cursor is detected from its payload, not `CURSOR_VERSION`.** Claude Code run
   inside Cursor's integrated terminal can inherit Cursor's environment variables,
   which would misroute Claude Code's own hooks. Cursor payloads name their event in
   camelCase (`sessionStart`), and Claude Code and Codex use PascalCase
   (`SessionStart`). Detection keys on that.
3. **The plugin moves to `plugins/continuity/`** (added after Task 1, user decision).
   Codex silently ignores a marketplace plugin whose source is the repo root, in every
   form, and installs symlinked folders empty (verification.md → V3). Task 1b does the
   move. **From Task 2 on, every path is relative to `plugins/continuity/`** (the
   plugin root), except these repo-root files: `.claude-plugin/marketplace.json`,
   `docs/`, `specs/`, `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `LICENSE`, `.specify/`
   and `.github/`.
4. **Codex fixtures are hand-built** from Codex's docs and the evidence in
   verification.md, each marked `"_source": "unverified: built from docs"`, because
   no live Codex session was possible (Task 1). The live Codex run in Task 7 replaces
   them, after the user updates Codex and trusts the hooks.

## Global Constraints

- Python 3.9+ standard library only. No third-party import, ever (CLAUDE.md).
- Every hook exits 0, never blocks, and logs failures to `.continuity/errors.log` (FR-012).
- Memory writes stay detached background processes (FR-010).
- `errors.log` lines never carry payload content (data-model.md Failure Log Entry rule).
- No manifest names `hooks/hooks.json` (CONTINUI-48: Claude Code rejects it as a duplicate).
- All manifests carry the same `name` (`continuity`) and `version`.
- Claude Code behaviour must not change: its payloads produce byte-identical output.
- Branch `feat/multi-agent`; merge to `develop` by reviewed PR only; `main` moves only by PR from `develop` (Constitution I, V).
- Commits: Conventional Commits with `(CONTINUI-N)` keys, no `Co-Authored-By` trailer.
- Terminology: "coding agent" on first use in each doc, "agent" after. Never "host".

## Review Focus

1. **Claude Code run inside Cursor's terminal.** Cursor's variables in the environment
   must not make a Claude Code payload be treated as Cursor's. Test in Task 2.
2. **A Codex patch touching files in two repositories, or with relative paths.** Each
   path resolves against `cwd`, each repository gets exactly one capture, and none is
   dropped. Tests in Tasks 2 and 3.
3. **A whitespace-only Codex patch.** It must not capture, the same as a
   whitespace-only Claude Code edit. Test in Task 2.
4. **Cursor start without `CURSOR_PROJECT_DIR`.** Fall back to
   `workspace_roots[0]`, then to the process cwd, and never crash. Test in Task 2.
5. **A Cursor event Continuity does not map** (e.g. a user adds `stop` to the config).
   It is a silent no-op with exit 0, not an error. Tests in Tasks 2 and 3.
6. **Hook code reading the plugin root from the environment.** Cursor runs hooks
   through a shared, long-lived worker whose environment can belong to another plugin
   (verification.md → Fix round 1). Hooks and `lib/` must locate files from
   `__file__`, never from `CLAUDE_PLUGIN_ROOT`/`CURSOR_PLUGIN_ROOT`. The final review
   checks this.

---

## File Structure

| File | Responsibility |
|---|---|
| `lib/agents.py` (new) | Detect the agent; convert its payload to Claude shape; format recall output; read paths from a Codex patch |
| `hooks/session-start.py` (modify) | Normalize input through `agents`; print output in the agent's shape |
| `hooks/capture-trigger.py` (modify) | Normalize input; classify each resulting payload; launch one writer per target repo |
| `hooks/session-end.py` (modify) | Normalize input to find the project root |
| `hooks/cursor-hooks.json` (new) | Cursor's hook config, same three scripts |
| `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `plugin.json` (new) | Per-agent manifests |
| `skills/continuity-checkpoint/SKILL.md` (new) | Checkpoint for Codex, which loads skills but not commands |
| `tests/test_agents.py` (new) | Unit tests for `lib/agents.py` |
| `tests/test_agent_hooks.py` (new) | Hook scripts driven by Codex and Cursor payloads |
| `tests/test_agent_packaging.py` (new) | Manifests and `cursor-hooks.json` |
| `tests/fixtures/agents/` (new) | Payloads recorded live in Task 1 |
| `docs/install.md`, `README.md`, `CLAUDE.md`, `.specify/memory/constitution.md`, `CHANGELOG.md` (modify) | Docs, amendment, release notes |

---

## Task 0: Track the work

- [ ] **Step 1:** Run `/pm-plan` for this plan against Jira project `CONTINUI`: an Epic
  "Continuity on Codex and Cursor", with one Story per task below (Tasks 1–8). The
  user approves the tree preview before anything is created.
- [ ] **Step 2:** Record the created keys in this file's task headings (e.g.
  `Task 2 (CONTINUI-6x)`), and use them in every commit.

---

## Task 1 (CONTINUI-56): Live verification spike (V1–V5) and recorded payloads

**Files:**
- Create: `tests/fixtures/agents/{claude,codex,cursor}/*.json` (recorded, scrubbed)
- Create: `specs/002-multi-agent/verification.md`
- Scratch only, never committed: a recorder plugin under the session scratchpad

**Interfaces:**
- Produces: fixture files named `<agent>/<event>.json`, each holding a scrubbed stdin
  payload and a `"_env"` object of the relevant environment variables. Tasks 2 and 3
  load them.

- [ ] **Step 1: Build a throwaway recorder plugin** in the scratchpad (`$S/recorder`).
  It contains copies of `.claude-plugin/`, the new `.codex-plugin/plugin.json`
  and `.cursor-plugin/plugin.json` from Task 4 Step 3, and a single script
  `record.py`:

```python
import json, os, sys, time
out = os.path.join(os.environ.get("RECORD_DIR", "/tmp"), "%d-%d.json" % (time.time() * 1000, os.getpid()))
keep = ("CURSOR_PROJECT_DIR", "CURSOR_VERSION", "CLAUDE_PROJECT_DIR", "PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT", "CURSOR_PLUGIN_ROOT")
data = {"stdin": sys.stdin.read(), "env": {k: os.environ[k] for k in keep if k in os.environ}, "argv": sys.argv}
open(out, "w").write(json.dumps(data, indent=2))
print("{}")
```

  Its `hooks/hooks.json` wires `SessionStart`, `PostToolUse` (matcher
  `Edit|Write|MultiEdit|Bash`) and `SessionEnd` to `python3 "${CLAUDE_PLUGIN_ROOT}/record.py"`.
  Its `hooks/cursor-hooks.json` wires `sessionStart`, `afterFileEdit`,
  `afterShellExecution` and `sessionEnd` the same way. Export
  `RECORD_DIR=$S/recorded` before each run.

- [ ] **Step 2: Find each agent's local-install path.** Run `codex plugin --help`,
  `codex --help | grep -i -A3 plugin` and `cursor-agent --help | grep -i -A3 plugin`.
  Record the exact marketplace-add and install commands in `verification.md`. If an
  agent can only install from a Git URL, push the recorder to a scratch branch of this
  repo and delete that branch at the end of the task.

- [ ] **Step 3: Record Codex (V2, V4, V5).** Install the recorder and trust its hooks
  when prompted. In a scratch git repo, run
  `codex exec "Create notes/a.txt containing hello, then edit it to say hello world, then run git status"`.
  Expect recordings for `SessionStart`, at least one `PostToolUse` with `tool_name`
  `apply_patch`, one for `Bash`, and `SessionEnd`. Note the exact shape of
  `tool_input.command`: string or list, and the header lines.

- [ ] **Step 4: Record Cursor (V1, V5).** Install the recorder, then in a scratch repo
  run `cursor-agent -p "Create notes/a.txt containing hello, then run git status"`.
  Expect `sessionStart`, `afterFileEdit`, `afterShellExecution` and `sessionEnd`.
  **V1:** confirm no recording carries a PascalCase `hook_event_name`, which would mean
  Cursor also loaded `hooks/hooks.json`. Also confirm **every** Cursor payload carries
  `hook_event_name` in camelCase, because `detect_agent` depends on it. If any lacks
  it, pick a field present in every Cursor payload and in no Claude Code or Codex one
  (for example `cursor_version` or `conversation_id`). Rewrite `detect_agent` in Task 2
  to use it before starting Task 2.

- [ ] **Step 5: Record Claude Code** with `claude -p --plugin-dir $S/recorder` and the
  same prompt, as the byte-identical baseline.

- [ ] **Step 6: Check V3.** Install the **real** plugin in Codex and in Cursor from this
  branch's marketplace (`source: "./"`). If either refuses a root-level source,
  **stop and ask the user** before going further. The fallback is moving the plugin
  into a subfolder.

- [ ] **Step 7: Scrub and save the fixtures.** For each recording, remove or replace
  every user-identifying value: emails, user names in paths (`/Users/<name>` becomes
  `/home/user`), and session and conversation ids (use `"test-session"`). Save to
  `tests/fixtures/agents/<agent>/<event>.json` as
  `{"payload": {...}, "_env": {...}}`, one file per event:
  `SessionStart.json`, `PostToolUse-apply_patch.json`, `PostToolUse-Bash.json`,
  `SessionEnd.json`, `sessionStart.json`, `afterFileEdit.json`,
  `afterShellExecution.json`, `sessionEnd.json`, `PostToolUse-Edit.json`.
  Then run `gitleaks detect --no-git --source tests/fixtures/agents` and expect
  `no leaks found`.

- [ ] **Step 8: Write `verification.md`**: one row per V1–V5 with the observed result,
  the exact install commands, and any difference from `design.md`'s capability table.
  If an observed shape differs from what Task 2's code assumes (event names, field
  names, patch header format), update Task 2's code in this plan **before** starting
  Task 2, and say so in `verification.md`.

- [ ] **Step 9: Commit**

```bash
git add tests/fixtures/agents specs/002-multi-agent/verification.md
git commit -m "test(CONTINUI-56): record live Codex, Cursor and Claude Code hook payloads"
```

---

## Task 1b (CONTINUI-59): Move the plugin into `plugins/continuity/`

**Files:**
- Move (`git mv`): `.claude-plugin/plugin.json`, `hooks/`, `lib/`, `commands/`,
  `templates/`, `tests/` → `plugins/continuity/<same path>`
- Keep at repo root: `.claude-plugin/marketplace.json`, `docs/`, `specs/`,
  `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `LICENSE`, `.specify/`, `.github/`, `.gitignore`
- Modify: `.claude-plugin/marketplace.json` (source), `.github/workflows/tests.yml`,
  `CLAUDE.md`, `docs/install.md` (paths only), any test that reads a repo-root file
- Test: `plugins/continuity/tests/test_layout.py` (new)

**Interfaces:**
- Produces: the plugin root `plugins/continuity/`, which every later task's paths are
  relative to. `PROJECT_ROOT` = repo root = plugin root `/../..`.

- [ ] **Step 1: Write the failing test** at `tests/test_layout.py` (before the move,
  so it moves with the rest):

```python
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
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `python3 -m unittest tests.test_layout -v` (from the repo root, before the move)
Expected: FAIL: `PROJECT_ROOT` resolves two levels above the repo, so
`marketplace.json` is not found (or the source is `"./"`).

- [ ] **Step 3: Move**

```bash
mkdir -p plugins/continuity/.claude-plugin
git mv .claude-plugin/plugin.json plugins/continuity/.claude-plugin/plugin.json
git mv hooks lib commands templates tests plugins/continuity/
```

  Set `.claude-plugin/marketplace.json`'s continuity entry to `"source": "./plugins/continuity"`.

- [ ] **Step 4: Repair references to repo-root files.** Run both suites from the
  plugin root. Every failure should be a path to a repo-root file (`docs/`,
  `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `LICENSE`, `.github/`). Fix
  each one by resolving it from `PROJECT_ROOT` (plugin root `/../..`). In
  `tests/run_tests.sh`, export `PROJECT_ROOT="$(cd "$REPO_ROOT/../.." && pwd)"`
  next to `REPO_ROOT`. **Change paths only. Never weaken or delete an assertion**
  (Constitution III). The one exception is `tests/test_structure*.sh`: they assert
  the plugin tree's own directories, so drop `docs` from their plugin-directory
  lists and add one check that `$PROJECT_ROOT/docs` exists. Record each changed
  test in the report.

- [ ] **Step 5: Point everything else at the new root**
  - `.github/workflows/tests.yml`: add `working-directory: plugins/continuity` to
    both test steps.
  - `CLAUDE.md` Build & test block: `cd plugins/continuity` before the two
    commands. Update the Layout block to show `plugins/continuity/` holding
    `.claude-plugin/plugin.json`, `hooks/`, `commands/`, `lib/`, `templates/`
    and `tests/`, with `.claude-plugin/marketplace.json`, `docs/` and `specs/` at
    the root.
  - `docs/install.md`: any `lib/<file>` reference becomes
    `plugins/continuity/lib/<file>`.

- [ ] **Step 6: Verify**

Run from `plugins/continuity/`: `python3 tests/run_tests.py` → `OK` (now including `test_layout`),
and `bash tests/run_tests.sh` → `0 failed`.
Run from the repo root: `claude plugin validate .` → `Validation passed`.
Then one live load check (one Haiku session):
`claude -p --model haiku --plugin-dir plugins/continuity --settings <scratch settings disabling installed continuity> --output-format stream-json --verbose "Reply OK" < /dev/null`
Expected: the `init` event's `plugin_errors` has no `continuity@inline` entry, and a
SessionStart `hook_response` contains `[Continuity]`.

- [ ] **Step 7: Commit**

```bash
git add -A plugins/continuity .claude-plugin/marketplace.json .github/workflows/tests.yml CLAUDE.md docs/install.md
git status --short   # must show only renames under plugins/continuity/ plus the listed files
git commit -m "refactor(plugin): move the plugin into plugins/continuity/ so Codex can install it (CONTINUI-59)"
```

---

## Task 2 (CONTINUI-57): `lib/agents.py`

**Files:**
- Create: `lib/agents.py`
- Test: `tests/test_agents.py`

**Interfaces:**
- Produces:
  - `CLAUDE, CODEX, CURSOR`: the strings `"claude"`, `"codex"`, `"cursor"`
  - `detect_agent(payload: dict) -> str`
  - `normalize(payload: dict, env: Mapping[str, str]) -> list[dict]`: Claude-shaped
    payloads; `[]` means "nothing to do"
  - `format_context(agent: str, event_name: str, text: str) -> str`: one line of JSON
  - `patch_paths(patch, cwd) -> list[str]`: absolute paths, first-seen order, no duplicates

- [ ] **Step 1: Write the failing tests** in `tests/test_agents.py`:

```python
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest tests.test_agents -v`
Expected: `ModuleNotFoundError: No module named 'lib.agents'`

- [ ] **Step 3: Write `lib/agents.py`**

```python
"""lib/agents.py — the one module that knows how coding agents differ.

Claude Code, Codex and Cursor call the same hook scripts with different
payloads (specs/002-multi-agent/design.md). normalize() turns any of them into
the Claude Code payload shape the hooks already handle; format_context() turns
recall text into the shape the calling agent reads. Pure functions: no store
access, no I/O.

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import json
import os
import re

CLAUDE = "claude"
CODEX = "codex"
CURSOR = "cursor"

# Cursor names events in camelCase; Claude Code and Codex in PascalCase. Keyed on
# the payload, not on CURSOR_* env vars, because Claude Code run inside Cursor's
# terminal can inherit those.
_CURSOR_EVENTS = {
    "sessionStart": "SessionStart",
    "sessionEnd": "SessionEnd",
    "afterFileEdit": "PostToolUse",
    "afterShellExecution": "PostToolUse",
}

_PATCH_HEADER = re.compile(
    r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$|^\*\*\* Move to: (.+?)\s*$", re.MULTILINE
)


def detect_agent(payload):
    event = payload.get("hook_event_name")
    if isinstance(event, str) and event[:1].islower():
        return CURSOR
    if payload.get("tool_name") == "apply_patch":
        return CODEX
    return CLAUDE


def normalize(payload, env):
    """Return Claude-shaped payloads for this hook call; [] means nothing to do."""
    agent = detect_agent(payload)
    if agent == CURSOR:
        return _from_cursor(payload, env)
    if agent == CODEX:
        return _from_codex_patch(payload)
    return [payload]


def format_context(agent, event_name, text):
    if agent == CURSOR:
        return json.dumps({"additional_context": text})
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}}
    )


def patch_paths(patch, cwd):
    """Absolute paths named by a Codex apply_patch, first-seen order."""
    paths = []
    for match in _PATCH_HEADER.finditer(patch):
        path = match.group(1) or match.group(2)
        if not os.path.isabs(path):
            if not (isinstance(cwd, str) and cwd):
                continue
            path = os.path.join(cwd, path)
        path = os.path.normpath(path)
        if path not in paths:
            paths.append(path)
    return paths


def _cursor_root(payload, env):
    root = env.get("CURSOR_PROJECT_DIR")
    if root:
        return root
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots and isinstance(roots[0], str) and roots[0]:
        return roots[0]
    return None


def _from_cursor(payload, env):
    event = payload.get("hook_event_name")
    if event not in _CURSOR_EVENTS:
        return []
    out = {"cwd": _cursor_root(payload, env), "hook_event_name": _CURSOR_EVENTS[event]}
    if event == "afterFileEdit":
        out["tool_name"] = "MultiEdit"
        out["tool_input"] = {
            "file_path": payload.get("file_path"),
            "edits": payload.get("edits") or [],
        }
    elif event == "afterShellExecution":
        out["tool_name"] = "Bash"
        out["tool_input"] = {"command": payload.get("command") or ""}
    return [out]


def _patch_text(payload):
    command = (payload.get("tool_input") or {}).get("command")
    if isinstance(command, list):
        return "\n".join(part for part in command if isinstance(part, str))
    return command if isinstance(command, str) else ""


def _changes_content(patch):
    """False only when every +/- line pair differs by whitespace alone."""
    removed, added = [], []
    for line in patch.splitlines():
        if line.startswith("***") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    if not removed and not added:
        return True
    return "".join("".join(removed).split()) != "".join("".join(added).split())


def _from_codex_patch(payload):
    patch = _patch_text(payload)
    if patch and not _changes_content(patch):
        return []
    paths = patch_paths(patch, payload.get("cwd"))
    if not paths:
        # Unparseable patch: capture against the session root, like the Bash trigger.
        return [dict(payload, tool_name="Edit", tool_input={})]
    return [dict(payload, tool_name="Edit", tool_input={"file_path": path}) for path in paths]
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `python3 -m unittest tests.test_agents -v`
Expected: every test `ok`. Then run `python3 tests/run_tests.py` and expect `OK`.

- [ ] **Step 5: Commit**

```bash
git add lib/agents.py tests/test_agents.py
git commit -m "feat(lib): detect the coding agent and normalize its hook payloads (CONTINUI-57)"
```

---

## Task 3 (CONTINUI-58): Route the three hooks through `lib/agents.py`

**Files:**
- Modify: `hooks/session-start.py` (`main`, imports)
- Modify: `hooks/capture-trigger.py` (`main`, imports)
- Modify: `hooks/session-end.py` (`main`, imports)
- Test: `tests/test_agent_hooks.py`

**Interfaces:**
- Consumes: `agents.detect_agent`, `agents.normalize`, `agents.format_context` (Task 2)
- Produces: hook scripts that accept all three agents' payloads, and whose Claude Code
  behaviour is unchanged.

- [ ] **Step 1: Write the failing tests** in `tests/test_agent_hooks.py`:

```python
"""tests/test_agent_hooks.py — the hook scripts driven by Codex and Cursor payloads."""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)


def load_hook(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(REPO_ROOT, "hooks", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capture_trigger = load_hook("capture-trigger")
session_end = load_hook("session-end")
session_start = load_hook("session-start")


def run_main(module, payload, env=None):
    stdin = io.StringIO(json.dumps(payload))
    with mock.patch.object(sys, "stdin", stdin), mock.patch.dict(os.environ, env or {}, clear=False):
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            code = module.main()
    return code, out.getvalue()


class TestCaptureTriggerAcrossAgents(unittest.TestCase):
    def test_codex_patch_across_two_repos_launches_one_writer_each(self):
        # Review Focus 2
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            os.mkdir(os.path.join(a, ".git"))
            os.mkdir(os.path.join(b, ".git"))
            patch = "*** Update File: %s/x.py\n-1\n+2\n*** Update File: %s/y.py\n-1\n+2\n*** Update File: %s/z.py\n-1\n+2\n" % (a, b, b)
            payload = {"hook_event_name": "PostToolUse", "tool_name": "apply_patch", "cwd": a, "tool_input": {"command": patch}}
            with mock.patch.object(capture_trigger, "launch_writer") as launch:
                self.assertEqual(run_main(capture_trigger, payload)[0], 0)
            self.assertEqual(sorted(c.args[0] for c in launch.call_args_list), sorted([a, b]))

    def test_cursor_after_file_edit_launches_writer_in_project(self):
        with tempfile.TemporaryDirectory() as root:
            payload = {"hook_event_name": "afterFileEdit", "file_path": os.path.join(root, "a.py"), "edits": [{"old_string": "a", "new_string": "b"}]}
            with mock.patch.object(capture_trigger, "launch_writer") as launch:
                run_main(capture_trigger, payload, {"CURSOR_PROJECT_DIR": root})
            launch.assert_called_once_with(root, "file-change")

    def test_cursor_whitespace_only_edit_launches_nothing(self):
        payload = {"hook_event_name": "afterFileEdit", "file_path": "/r/a.py", "edits": [{"old_string": "a b", "new_string": "a  b"}]}
        with mock.patch.object(capture_trigger, "launch_writer") as launch:
            run_main(capture_trigger, payload, {"CURSOR_PROJECT_DIR": "/r"})
        launch.assert_not_called()

    def test_unmapped_cursor_event_is_a_silent_no_op(self):
        # Review Focus 5
        with mock.patch.object(capture_trigger, "launch_writer") as launch, mock.patch.object(capture_trigger, "_log") as log:
            code, out = run_main(capture_trigger, {"hook_event_name": "stop"}, {"CURSOR_PROJECT_DIR": "/r"})
        self.assertEqual((code, out), (0, ""))
        launch.assert_not_called()
        log.assert_not_called()


class TestSessionEndAcrossAgents(unittest.TestCase):
    def test_cursor_session_end_flushes_the_project(self):
        with mock.patch.object(session_end, "launch_writer") as launch:
            run_main(session_end, {"hook_event_name": "sessionEnd"}, {"CURSOR_PROJECT_DIR": "/work/repo"})
        launch.assert_called_once_with("/work/repo")


class TestSessionStartAcrossAgents(unittest.TestCase):
    def test_cursor_gets_additional_context_for_its_project(self):
        with tempfile.TemporaryDirectory() as root:
            code, out = run_main(session_start, {"hook_event_name": "sessionStart"}, {"CURSOR_PROJECT_DIR": root})
            self.assertEqual(code, 0)
            context = json.loads(out)["additional_context"]
            self.assertIn(os.path.join(root, ".continuity", ".staged"), context)

    def test_codex_start_output_is_the_claude_shape(self):
        with tempfile.TemporaryDirectory() as root:
            _, out = run_main(session_start, {"hook_event_name": "SessionStart", "cwd": root})
            self.assertIn("additionalContext", json.loads(out)["hookSpecificOutput"])

    def test_claude_output_unchanged_with_cursor_env_present(self):
        # Review Focus 1
        with tempfile.TemporaryDirectory() as root:
            _, plain = run_main(session_start, {"hook_event_name": "SessionStart", "cwd": root})
            _, with_env = run_main(session_start, {"hook_event_name": "SessionStart", "cwd": root}, {"CURSOR_VERSION": "2.0", "CURSOR_PROJECT_DIR": "/elsewhere"})
            self.assertEqual(plain, with_env)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `python3 -m unittest tests.test_agent_hooks -v`
Expected: the Cursor and Codex cases FAIL (the scripts only read `cwd` from the payload today).

- [ ] **Step 3: Modify `hooks/capture-trigger.py`.** Add the import after the
  `PLUGIN_ROOT` definition, and replace the body of `main()` after the
  `isinstance(parsed, dict)` check:

```python
sys.path.insert(0, PLUGIN_ROOT)
from lib import agents  # noqa: E402  stdlib-only; keeps the no-op path cheap
```

```python
    try:
        payloads = agents.normalize(parsed, os.environ)
    except Exception as error:  # fail open; never raise out of a hook
        _log(parsed.get("cwd") or os.getcwd(), "payload-shape", type(error).__name__)
        return 0

    launches = []
    for payload in payloads:
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            continue
        try:
            trigger_kind = classify(payload)
        except Exception:
            trigger_kind = None
        if not trigger_kind:
            continue
        target = project_root_for(payload)
        target = target if isinstance(target, str) and target else cwd
        if (target, trigger_kind) not in launches:
            launches.append((target, trigger_kind))

    for target, trigger_kind in launches:
        launch_writer(target, trigger_kind)
    return 0
```

  Update the module docstring's CONTINUI-47 paragraph with one sentence: "Codex and
  Cursor payloads are converted to this shape by `lib/agents.py` first; a Codex patch
  naming several files yields one writer per distinct repository."

- [ ] **Step 4: Modify `hooks/session-end.py`.** Add the same import. Replace
  `cwd = parsed.get("cwd")` in `main()` with:

```python
    try:
        payloads = agents.normalize(parsed, os.environ)
    except Exception as error:  # fail open
        _log(parsed.get("cwd") or os.getcwd(), "payload-shape", type(error).__name__)
        return 0
    cwd = payloads[0].get("cwd") if payloads else None
```

- [ ] **Step 5: Modify `hooks/session-start.py`.** Change the import line to
  `from lib import agents` alongside the existing ones. In `main()`, replace the first
  three lines, and the output lines, with:

```python
    raw_payload = read_payload()
    agent = agents.detect_agent(raw_payload)
    try:
        normalized = agents.normalize(raw_payload, os.environ)
    except Exception as error:  # fail open
        continuity_log(continuity_dir(os.getcwd()), "session-start-load", "payload-shape", type(error).__name__)
        normalized = []
    payload = normalized[0] if normalized else {}
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()
```

```python
    print(agents.format_context(agent, HOOK_EVENT_NAME, context))
    return 0
```

  This deletes the old `output = {...}` dict building. The Claude Code output stays
  byte-identical, which `test_claude_output_is_byte_identical_to_v012` in Task 2 pins.

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `python3 -m unittest tests.test_agent_hooks -v`, then `python3 tests/run_tests.py`, then `bash tests/run_tests.sh`
Expected: all `ok`; `OK`; `0 failed`. Every existing Claude Code test passes
untouched. If one fails, the change broke Claude Code behaviour: fix the code, not the
test (Constitution III).

- [ ] **Step 7: Commit**

```bash
git add hooks/session-start.py hooks/capture-trigger.py hooks/session-end.py tests/test_agent_hooks.py
git commit -m "feat(hooks): accept Codex and Cursor hook payloads via lib/agents.py (CONTINUI-58)"
```

---

## Task 4 (CONTINUI-59): Cursor hook config and per-agent manifests

**Files:**
- Create: `hooks/cursor-hooks.json`, `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `plugin.json`
- Modify: `.claude-plugin/marketplace.json` (description only)
- Test: `tests/test_agent_packaging.py`

**Interfaces:**
- Consumes: the three hook scripts (Task 3)
- Produces: manifests whose `version` Task 8 bumps together

- [ ] **Step 1: Write the failing tests** in `tests/test_agent_packaging.py`:

```python
"""tests/test_agent_packaging.py — one plugin, one manifest per coding agent."""

import ast
import json
import os
import sys
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MANIFESTS = [".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json", "plugin.json"]
CURSOR_EVENTS = {"sessionStart", "sessionEnd", "afterFileEdit", "afterShellExecution"}


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
```

- [ ] **Step 2: Run and confirm they fail**

Run: `python3 -m unittest tests.test_agent_packaging -v`
Expected: `FileNotFoundError` for `.codex-plugin/plugin.json`.

- [ ] **Step 3: Create the files.**

`hooks/cursor-hooks.json`:

```json
{
  "version": 1,
  "hooks": {
    "sessionStart": [{ "command": "python3 \"${CURSOR_PLUGIN_ROOT}/hooks/session-start.py\"" }],
    "afterFileEdit": [{ "command": "python3 \"${CURSOR_PLUGIN_ROOT}/hooks/capture-trigger.py\"" }],
    "afterShellExecution": [{ "command": "python3 \"${CURSOR_PLUGIN_ROOT}/hooks/capture-trigger.py\"" }],
    "sessionEnd": [{ "command": "python3 \"${CURSOR_PLUGIN_ROOT}/hooks/session-end.py\"" }]
  }
}
```

`.codex-plugin/plugin.json`:

```json
{
  "name": "continuity",
  "version": "0.1.2",
  "description": "Cross-session memory for coding agents: persists project-scoped context under .continuity/ as plain Markdown, recalls a bounded subset at session start, captures after meaningful edits and commits, and fails open on any error.",
  "author": { "name": "Navjyot Nishant" },
  "repository": "https://github.com/navjyotnishant/continuity",
  "license": "MIT",
  "keywords": ["memory", "context", "sessions", "continuity"],
  "skills": "./skills/",
  "interface": {
    "displayName": "Continuity",
    "shortDescription": "Remembers a project's decisions, tasks and learnings across sessions",
    "longDescription": "Keeps plain-Markdown memory under .continuity/ in each project. Recalls a bounded, labelled summary when a session starts, records notes after meaningful edits and commits, and never blocks or breaks a session if anything goes wrong.",
    "developerName": "Navjyot Nishant",
    "category": "Developer Tools",
    "capabilities": ["Interactive"],
    "defaultPrompt": ["What did we decide last session?", "Checkpoint what we learned so far"]
  }
}
```

`.cursor-plugin/plugin.json` and `plugin.json`: same `name`, `version`, `description`,
`author`, `license` and `keywords` as above. The Cursor one adds
`"hooks": "./hooks/cursor-hooks.json"`. The root one adds
`"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"`.
`MIT` matches the repo's `LICENSE` file.

In `.claude-plugin/marketplace.json`, set the plugin entry's `description` to the
description above.

- [ ] **Step 4: Run and confirm they pass** (the skill test waits for Task 5)

Run: `python3 -m unittest tests.test_agent_packaging -v`
Expected: all pass except `test_codex_manifest_points_at_skills`, which passes after Task 5.

- [ ] **Step 5: Commit**

```bash
git add hooks/cursor-hooks.json .codex-plugin .cursor-plugin plugin.json .claude-plugin/marketplace.json tests/test_agent_packaging.py
git commit -m "feat(plugin): add Codex and Cursor manifests and Cursor hook config (CONTINUI-59)"
```

---

## Task 5 (CONTINUI-60): Checkpoint skill for Codex

**Files:**
- Create: `skills/continuity-checkpoint/SKILL.md`
- Test: `tests/test_agent_packaging.py::TestManifests::test_codex_manifest_points_at_skills` (from Task 4)

- [ ] **Step 1: Confirm the failing test**

Run: `python3 -m unittest tests.test_agent_packaging.TestManifests.test_codex_manifest_points_at_skills -v`
Expected: FAIL (no `SKILL.md`).

- [ ] **Step 2: Write `skills/continuity-checkpoint/SKILL.md`**

````markdown
---
name: continuity-checkpoint
description: Checkpoint what this session has learned into the project's .continuity/ memory right now. Use when the user asks to checkpoint, save, or remember the session's decisions, tasks or learnings.
---

# Continuity checkpoint

Persist this session's memory-worthy content now, instead of waiting for the next
automatic trigger.

## Step 1: find the project root

Run `pwd` and use its output as `<root>`. Every path below is under that absolute
root, never under the coding agent's own memory directory.

## Step 2: stage what is worth keeping

For each thing a future session would need and could not re-derive from the code,
create one file:

```text
<root>/.continuity/.staged/<kind>-<UTC-timestamp>-<n>.md
```

- `<kind>` is exactly one of `decision`, `task`, `learning`, `handoff`.
- `<UTC-timestamp>` looks like `20260927T140501Z`; `<n>` is any integer that keeps two
  notes in the same second apart.
- The body is plain Markdown. A first-line heading becomes the entry's title.

Stage nothing if nothing qualifies. An empty checkpoint is a valid outcome.

## Step 3: consolidate

Run the writer. `<plugin>` is this plugin's root: `$CLAUDE_PLUGIN_ROOT` or
`$PLUGIN_ROOT` if either is set, otherwise the directory two levels above this
`SKILL.md`.

```bash
python3 "<plugin>/lib/write_memory.py" "<root>" explicit-checkpoint
```

## Step 4: report

Relay the writer's one-line result: either `Checkpoint written to …` plus one line per
note captured, or exactly `Nothing new to checkpoint`. Never commit `.continuity/`
with git; that is the developer's decision.
````

- [ ] **Step 3: Run the packaging tests**

Run: `python3 -m unittest tests.test_agent_packaging -v`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add skills/continuity-checkpoint/SKILL.md
git commit -m "feat(skills): add the checkpoint skill for Codex, which loads skills not commands (CONTINUI-60)"
```

---

## Task 6 (CONTINUI-61): Docs and the constitution amendment

**Files:**
- Modify: `docs/install.md`, `README.md`, `CLAUDE.md`, `.specify/memory/constitution.md`
- Test: `bash tests/run_tests.sh` (existing doc tests must stay green)

- [ ] **Step 1: `docs/install.md`.** Add an "Install per coding agent" section at the
  top, above the existing git-tracking content:

````markdown
## Install per coding agent

Continuity is one plugin with one manifest per coding agent. Install it from this
repository's marketplace in whichever agent you use:

### Claude Code

```text
/plugin marketplace add navjyotnishant/continuity
/plugin install continuity@continuity
```

Start a new session afterwards.

### Codex

Add the marketplace `https://github.com/navjyotnishant/continuity.git` in Codex's plugin
settings (CLI: <exact command recorded in specs/002-multi-agent/verification.md>),
then install `continuity`. Codex asks you to **review and trust the plugin's hooks**
once. Until you do, it installs but never recalls or captures. Codex loads skills,
not commands, so checkpoint with the `continuity-checkpoint` skill.

### Cursor

Add the same repository as a team or local marketplace and install `continuity`
(CLI: <exact command recorded in specs/002-multi-agent/verification.md>). Cursor reads
`.cursor-plugin/plugin.json` and its hooks from `hooks/cursor-hooks.json`.

### Claude Desktop (Cowork): not supported

Cowork does not run plugin hooks, so Continuity can neither recall nor capture there
([anthropics/claude-code#40495](https://github.com/anthropics/claude-code/issues/40495)).
This section changes once that is fixed.

### Updating

Refresh the marketplace, reinstall, and start a new session. A running session keeps
the version it started with.
````

  Replace both `<exact command …>` markers with the commands Task 1 Step 2 recorded.
  They are markers for the executor, not text to ship: `grep -n "<exact command" docs/install.md`
  must print nothing before committing.

- [ ] **Step 2: `README.md` and `CLAUDE.md`.** Replace "Claude Code plugin" wording
  that describes what Continuity *is* with "plugin for Claude Code, Codex and Cursor".
  Find the sites with `grep -n -i "claude code plugin\|a claude code" README.md CLAUDE.md`.
  In CLAUDE.md's Layout block, add `.codex-plugin/  .cursor-plugin/  Codex and Cursor manifests`
  and `skills/  checkpoint skill (Codex loads skills, not commands)`. Also add
  `lib/agents.py` to the `lib/` description.

- [ ] **Step 3: Constitution.** In `.specify/memory/constitution.md`:
  - Replace the **Distribution shape** bullet with the text in `design.md`
    → "Constitution amendment".
  - In **Feel unchanged** and **Fail open**, change "Claude Code" to "the coding agent".
    The four occurrences are at lines 65, 84 and 88; re-grep before editing.
  - Set the footer to `**Version**: 1.1.0 | **Ratified**: 2026-09-11 | **Last Amended**: <today>`.
  - Prepend a Sync Impact Report entry: `Version change: 1.0.0 → 1.1.0 (MINOR);
    Modified: Additional Constraints → Distribution shape, Feel unchanged, Fail open;
    reason: multi-agent support (specs/002-multi-agent).`

- [ ] **Step 4: Run the suites**

Run: `python3 tests/run_tests.py && bash tests/run_tests.sh`
Expected: `OK` and `0 failed`. If `test_install_docs*.sh` fail on moved headings,
update the heading the test looks for only when the doc's meaning is unchanged, and
say so in the commit body.

- [ ] **Step 5: Commit**

```bash
git add docs/install.md README.md CLAUDE.md .specify/memory/constitution.md
git commit -m "docs: install per coding agent, Desktop unsupported, constitution 1.1.0 (CONTINUI-61)"
```

---

## Task 7 (CONTINUI-62): Live quickstart in each agent

**Files:**
- Create: `specs/002-multi-agent/live-results.md`

- [ ] **Step 1: Confirm cost with the user**: about 30 short headless sessions (10 per
  agent). Do not start without a yes.

- [ ] **Step 2: For each agent, install the plugin from this branch** the way a user
  would, using the Task 1 commands. Use a fresh scratch git repo per agent. Disable the
  globally installed Claude Code copy for the Claude run (as in T037:
  `--settings` with `enabledPlugins` false).

- [ ] **Step 3: Run quickstart Scenarios 1, 3, 4 and 5** (`specs/001-continuity/quickstart.md`)
  in each agent with its headless runner:
  - `claude -p --model sonnet`
  - `codex exec`
  - `cursor-agent -p`

  Use the same prompts and injections as the T037 run (comment on CONTINUI-43).
  Scenario 2 stays out of scope, as in T037.

- [ ] **Step 4: Write `live-results.md`**: one Expected-vs-Actual table per agent.
  File every deviation as a Jira task via `/pm-task` under the Epic **before** this
  task counts as done. If an agent's headless runner cannot run plugin hooks (V5), say
  so in the table rather than marking it passed.

- [ ] **Step 5: Commit**

```bash
git add specs/002-multi-agent/live-results.md
git commit -m "test(CONTINUI-62): live quickstart results for Claude Code, Codex and Cursor"
```

---

## Task 8 (CONTINUI-63): Release v0.2.0

- [ ] **Step 1: Bump versions together.** Set `"version": "0.2.0"` in all four
  manifests, and `"plugin_version": "0.2.0"` in `templates/metadata.json.tmpl`.
  `test_every_manifest_shares_name_and_version` enforces the match.

- [ ] **Step 2: CHANGELOG.** Under `## [0.2.0] - <today>`:

```markdown
### Added

- Continuity now installs and runs in **Codex** and **Cursor** as well as Claude Code,
  from the same GitHub marketplace. Each coding agent recalls at session start,
  captures after meaningful edits and commits, and flushes at session end.
- A `continuity-checkpoint` skill, for Codex, which loads skills but not commands.

### Changed

- Install docs are now per coding agent. Claude Desktop (Cowork) is documented as
  unsupported, because it does not run plugin hooks.
```

  Update the compare links at the bottom (`[Unreleased]` → `v0.2.0...HEAD`, add `[0.2.0]`).

- [ ] **Step 3: Verify, then commit**

Run: `python3 tests/run_tests.py && bash tests/run_tests.sh && gitleaks git --log-opts="develop..HEAD" --no-banner`
Expected: `OK`, `0 failed`, `no leaks found`.

```bash
git add .claude-plugin/plugin.json .codex-plugin/plugin.json .cursor-plugin/plugin.json plugin.json templates/metadata.json.tmpl CHANGELOG.md
git commit -m "chore(release): v0.2.0 -- Codex and Cursor support"
```

- [ ] **Step 4: PR to develop.** Push, open a PR `feat/multi-agent` → `develop`, and
  wait for green CI. **Merge only on the user's explicit approval.**
- [ ] **Step 5: Tag and promote.** Tag `v0.2.0` (annotated, message `v0.2.0`) on the
  merge commit and push the tag. Open a PR `develop` → `main` (Constitution V). Merge
  it only on the user's approval.
- [ ] **Step 6: Hand over the user acceptance test** from `design.md`: in each app, add
  the marketplace, install, record a decision, and confirm a new session recalls it.
  Close the Epic once the user confirms.
