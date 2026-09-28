# Design: Continuity on Claude Code, Codex and Cursor (multi-agent support)

**Branch**: `feat/multi-agent` | **Date**: 2026-09-27 | **Status**: approved; amended 2026-09-27 (subfolder layout, after the Task 1 spike)
**Builds on**: [`specs/001-continuity`](../001-continuity/plan.md) (v0.1.2)

## Intent

A user installs Continuity from this repository's GitHub marketplace in **Claude
Code, Codex or Cursor** and gets the same behaviour everywhere: recall at session
start, capture after meaningful edits and commits, a flush at session end, with no
configuration of their own. The model to follow is `bug-triage-agent`
(`NjAIAgents/njagents/operations/bug-triage-agent`): one copy of the plugin, one
manifest per coding agent, one marketplace.

### Decisions already made (brainstorming, 2026-09-27)

| Question | Decision |
|---|---|
| Claude Desktop (Cowork) | **Unsupported, documented.** Cowork never runs plugin hooks ([anthropics/claude-code#40495](https://github.com/anthropics/claude-code/issues/40495), open). No MCP-server workaround. |
| How agent differences are handled | **Shared hook scripts + one normalizer** (`lib/agents.py`). No per-agent scripts, no user-visible flag. |
| Definition of "supported" | **Full quickstart (Scenarios 1, 3, 4, 5) passes live in each agent**, plus unit tests. |

### Non-goals

- Claude Desktop / Cowork, Claude.ai chat, ChatGPT chat. None of them run plugin hooks.
- Any new runtime, server, database or third-party package. Python 3.9+ stdlib only.
- Changing the `.continuity/` store format, selection budget or retention.

## Why hooks make this different from bug-triage-agent

`bug-triage-agent` is only skills and commands. All three agents read those in the same
Markdown format, so a second and third manifest are all it needs. Continuity's
behaviour lives in **hooks**, and each agent defines its own hook protocol. The plugin
must therefore ship one hook config per agent and code that speaks each agent's format.
Install and update stay identical to bug-triage-agent.

## Coding agent capabilities (researched 2026-09-27)

| | Claude Code | Codex (0.141) | Cursor (cursor-agent 2026.08) |
|---|---|---|---|
| Plugin hooks run | yes | yes, **after a one-time trust review** of the hook definitions | yes |
| Hook config found at | `hooks/hooks.json` (automatic) | `hooks/hooks.json` (automatic; same nested schema as Claude Code) | manifest `"hooks"` path, default `hooks/hooks.json`; **different schema** |
| Session start context | `hookSpecificOutput.additionalContext` | same | `additional_context` |
| Edit event | `PostToolUse` Edit/Write/MultiEdit; `tool_input.file_path` | `PostToolUse` `apply_patch` (matcher aliases `Edit`/`Write`); patch text in `tool_input.command` | `afterFileEdit`; `file_path` + `edits[]` |
| Shell event | `PostToolUse` Bash | `PostToolUse` Bash | `afterShellExecution`; `command` |
| Session end | `SessionEnd` | `SessionEnd` | `sessionEnd` |
| Project root | payload `cwd` | payload `cwd` | env `CURSOR_PROJECT_DIR` |
| Plugin root in commands | `${CLAUDE_PLUGIN_ROOT}` | `PLUGIN_ROOT`, alias `CLAUDE_PLUGIN_ROOT` | expands `${CURSOR_PLUGIN_ROOT}` and `${CLAUDE_PLUGIN_ROOT}` |
| Loads | hooks, commands, skills | hooks, **skills only** (no commands) | hooks, commands, skills, rules |

Sources: [Codex hooks](https://learn.chatgpt.com/docs/hooks),
[Cursor hooks](https://cursor.com/docs/hooks),
[Cursor plugins reference](https://cursor.com/docs/reference/plugins),
[Cowork hooks bug #40495](https://github.com/anthropics/claude-code/issues/40495),
[#27398](https://github.com/anthropics/claude-code/issues/27398).

## Architecture

```
hooks/
  session-start.py      reads/writes via lib/agents.py
  capture-trigger.py    reads via lib/agents.py (edited paths from agents.py)
  session-end.py        reads via lib/agents.py
  hooks.json            Claude Code + Codex (unchanged)
  cursor-hooks.json     NEW  Cursor schema, same three scripts, same command lines
lib/
  agents.py              NEW  the only module that knows agent differences
  (all other lib/ modules unchanged)
skills/
  continuity-checkpoint/SKILL.md   NEW  checkpoint for Codex (no commands there)
commands/continuity-checkpoint.md  kept (Claude Code, Cursor)
.claude-plugin/plugin.json         kept
.claude-plugin/marketplace.json    kept; description made agent-neutral
.codex-plugin/plugin.json          NEW  skills path + interface block
.cursor-plugin/plugin.json         NEW  "hooks": "./hooks/cursor-hooks.json"
plugin.json                        NEW  root manifest, agent-plugins.org schema
```

### `lib/agents.py`

Pure functions over (stdin text, environment). No store access, no I/O beyond what it
is given.

- `detect_agent(env, payload) -> "cursor" | "codex" | "claude"`
  - `cursor` when `CURSOR_VERSION` is set (only Cursor sets it).
  - `codex` when the payload's `tool_name` is `apply_patch`. That is the only place
    Codex differs from Claude Code. Its session-start and session-end input and
    output are identical, so they need no detection.
  - otherwise `claude`. Detection never uses the `CLAUDE_*` variables that Codex and
    Cursor set as compatibility aliases.
- `read_event(env, payload) -> Event(agent, kind, root, edited_paths, command)` where
  `kind` is `start | edit | shell | end | unknown`.
- `format_context(agent, text) -> str`: stdout JSON in the agent's shape.
- `patch_paths(patch_text) -> [path]`: paths from Codex `apply_patch` headers
  (`*** Add File:`, `*** Update File:`, `*** Delete File:`, `*** Move to:`), resolved
  against `root`.

The hook scripts keep their current structure. They get their input from `read_event`
and their output from `format_context` instead of hand-reading Claude Code's payload.

## Event mapping

| Continuity step | Claude Code | Codex | Cursor |
|---|---|---|---|
| Recall (`session-start.py`) | `SessionStart` | `SessionStart` | `sessionStart` |
| Capture on edit (`capture-trigger.py`) | `PostToolUse` Edit/Write/MultiEdit | `PostToolUse` `apply_patch` | `afterFileEdit` |
| Capture on commit (`capture-trigger.py`) | `PostToolUse` Bash | `PostToolUse` Bash | `afterShellExecution` |
| Flush (`session-end.py`) | `SessionEnd` | `SessionEnd` | `sessionEnd` |

Rules carried over unchanged to every agent:

- The staging instructions (CONTINUI-47) are always emitted, naming the absolute
  `.continuity/.staged/` path (CONTINUI-49).
- A capture targets the **edited file's own repository** (CONTINUI-47). A Codex patch
  that names several files yields every path; each resolves to its repository;
  duplicates collapse. One patch across two repositories checkpoints both.
- Whitespace-only edits are not meaningful. For Cursor this uses `edits[]`. For a
  Codex patch, the edit is meaningful unless every changed line differs only in
  whitespace.
- Writes stay detached background processes (FR-010). This matters more on Codex and
  Cursor, whose hook timeouts are stricter.

## Packaging and distribution

- **One marketplace, plugin in a subfolder.** `.claude-plugin/marketplace.json` at
  the repo root serves all three agents, as `njagents` does. The plugin itself lives
  in `plugins/continuity/`, and the marketplace entry's `source` is
  `"./plugins/continuity"`. Codex silently ignores a plugin sourced from the repo
  root, and installs symlinked folders empty (found in the Task 1 spike; see
  `verification.md`). Users add `github.com/navjyotnishant/continuity` as a
  marketplace in any agent and install `continuity`. Every path in the Architecture
  section is relative to `plugins/continuity/`.
- **Four manifests, one version.** `.claude-plugin/plugin.json`,
  `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json` and the root `plugin.json`
  carry the same `name` and `version`. `lib/migrate.py` keeps reading the version from
  `.claude-plugin/plugin.json`.
- **No manifest names `hooks/hooks.json`.** Claude Code rejects that as a duplicate
  (CONTINUI-48). Codex finds it automatically. Cursor's manifest names
  `hooks/cursor-hooks.json` instead.
- **Docs.** `docs/install.md` gets a section per agent, modelled on bug-triage-agent's
  `docs/03-installation.md`: add marketplace, install, Codex's trust prompt, updating,
  and a **Claude Desktop: not supported** section linking #40495. The README and
  CLAUDE.md stop describing Continuity as Claude-Code-only.
- **Release.** v0.2.0 (MINOR: new capability, nothing removed).

### Constitution amendment (MINOR, part of this change)

`Additional Constraints → Distribution shape` currently reads "ship strictly as a
claude-plugin distributed via a marketplace, on GitHub". Proposed text:

> **Distribution shape.** Continuity ships as a plugin for Claude Code, Codex and
> Cursor, from a single GitHub-hosted marketplace, with one manifest per coding agent and one
> shared copy of its code. No installation or use of Golang, and no other
> distribution shape, is in scope. Coding agents that do not run plugin hooks (currently
> Claude Desktop / Cowork) are documented as unsupported rather than worked around.

"Feel unchanged" and "Fail open" are read as applying to every supported coding agent, not
only Claude Code; their wording changes from "Claude Code" to "the coding agent".

## Error handling

No new failure modes. Every agent inherits the existing rules:

- Every hook exits 0 and never blocks. Failures go to `errors.log`.
- When no agent-specific signal is present, detection returns `claude`. A payload that does not
  match the detected agent's shape becomes `kind: unknown`. Recall then emits only the
  staging instructions, and capture does nothing. One `errors.log` line records
  `agent-detect` or `payload-shape` with the agent and event name, never payload
  content.
- `patch_paths` on unparseable patch text returns `[]`. The capture then falls back to
  the session root, as the Bash trigger does today.

## Verification before building on assumptions

These are checked live in the first implementation step. Each has a stated fallback.

| # | Check | If it fails |
|---|---|---|
| V1 | Cursor does **not** also load `hooks/hooks.json` when its manifest names `cursor-hooks.json` | Move Claude Code/Codex hooks into the manifest-free default and give Cursor an inline `hooks` object in `.cursor-plugin/plugin.json`; re-check |
| V2 | Exact Codex 0.141 `apply_patch` header lines and `PostToolUse` payload; env vars Codex sets | Adjust `patch_paths` / `detect` to the observed shape; recorded payloads become test fixtures |
| V3 | Codex and Cursor accept a marketplace plugin with `source: "./"` (repo root) | Stop and bring back to the user: the fallback is moving the plugin into a subfolder, a larger change |
| V4 | A Codex skill's shell can use `${CLAUDE_PLUGIN_ROOT}` | Skill resolves `lib/write_memory.py` relative to its own folder |
| V5 | `codex exec` and `cursor-agent -p` run plugin hooks headless | Say so, and mark that agent's live results as not obtained rather than passed |

## Testing

1. **`lib/agents.py` unit tests**, driven by payloads recorded during V2 and V1: every
   mapped event per agent maps to the right `Event`, and every agent's context output
   has the right shape. Also: multi-file Codex patch, whitespace-only patch and
   Cursor edit, unknown event, malformed JSON, missing root.
2. **Packaging tests**: the four manifests share name and version; `cursor-hooks.json`
   uses only Cursor event names and only names scripts that exist; no manifest names
   `hooks/hooks.json`; `agents.py` imports only the standard library.
3. **Live quickstart per agent**: Scenarios 1, 3, 4 and 5 in a scratch repo, installed
   from this repository's marketplace as a user would.
   - Claude Code: `claude -p`
   - Codex: `codex exec`, after trusting the hooks once
   - Cursor: `cursor-agent -p`

   The result is one Expected-vs-Actual table per agent, in the style of T037. Every
   deviation is filed before the work is called done. This is about 30 short headless
   sessions, confirmed with the user before they run.
4. **Existing suites** (`python3 tests/run_tests.py`, `bash tests/run_tests.sh`) stay
   green. Claude Code behaviour must not change: its recorded payloads pass through
   `agents.py` to byte-identical output.

### User acceptance (after merge)

In each app: add the marketplace, install Continuity (in Codex, trust its hooks),
record a decision in one session, and confirm a new session recalls it.

## Tracking

A `/pm-plan` tree (Epic, with Stories per agent plus packaging and docs) is created in
Jira project CONTINUI once this design is approved, before implementation.
