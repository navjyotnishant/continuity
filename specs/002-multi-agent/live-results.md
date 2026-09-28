# Live quickstart results (CONTINUI-62)

Ran 2026-09-28 against `claude` 2.1.278, `cursor-agent` 2026.09.26-dd393fe, and
`/opt/homebrew/bin/codex` (codex-cli) 0.157.1, all loading the plugin at
`plugins/continuity/` from branch `feat/multi-agent` (HEAD `f5995a4`) — Claude Code
and Cursor via `--plugin-dir`, Codex via its already-installed
`continuity@continuity` plugin (git-sourced marketplace tracking this same branch and
commit, confirmed by reading `~/.codex/.tmp/marketplaces/continuity/.git/HEAD` and
`git log`). Scenario 2 stays out of scope, as in T037. Every scratch repo lives under
`/private/tmp/claude-501/.../scratchpad/t7/<agent>/<scenario>.<rand>/` and was left in
place (never `rm -rf`'d).

**Session count: 33** (15 Claude Code + 16 Cursor + 2 Codex attempts), within the
confirmed ~30 budget and under the ~40 cap.

## Claude Code

Ran with `claude -p --plugin-dir plugins/continuity --settings <settings disabling
the globally-installed copy> --permission-mode acceptEdits --output-format
stream-json --verbose`. Scenario 1 used `--model sonnet` (needs real capture
reasoning); Scenarios 3/4/5 used `--model haiku` (hook-path only, pre-staged/edited
mechanically).

| # | Scenario | Expected | Actual | Result |
|---|---|---|---|---|
| 1 | Session A: decide + leave a task, staged per Continuity's instructions | `.continuity/decisions.md` and `.continuity/tasks.md` each gain an entry | Both files gained one entry each (`parse() raises ValueError...` / `UNFINISHED: input validation...`); `.staged/` empty afterward (consumed); `errors.log` empty | PASS |
| 1 | Session B (fresh, no tools): what was decided? | Injected context contains both items; answer consistent | `SessionStart` `additionalContext` contained the `[Continuity context — ...]` block with both the Active tasks and Recent decisions sections verbatim; session B's answer restated both correctly without re-reading files | PASS |
| 3.1 | Missing `.continuity/` (`rm -rf` before session) | Session starts normally, no error, store recreated | `RESULT is_error=false`; `.continuity/{state,tasks,decisions,learnings}.md` + `metadata.json` recreated by the very next `SessionStart` (seeded eagerly, ahead of the spec's "next write trigger" floor) | PASS |
| 3.2 | Corrupted `decisions.md` (`echo "not valid" >`) | Session starts normally; other files still load; `errors.log` gains `corrupted` for decisions.md; no user-facing error | `RESULT is_error=false`; `errors.log`: `... \| read-decisions \| corrupted \| no title and no entries` | PASS |
| 3.3 | Unreadable `state.md` (`chmod 000`) | Same as above, `unreadable` entry; chmod restored after | `RESULT is_error=false`; `errors.log`: `... \| read-state \| unreadable \| PermissionError`; restored to 644 | PASS |
| 3.4 | Write failure (`chmod 000 .continuity/`) + a meaningful edit | Turn completes normally, no visible delay/error; `errors.log` gains `write-failed` (or silently fails per the stated exception) | `RESULT is_error=false`, all hooks exit 0; `.continuity/errors.log` did not exist afterward — matches quickstart's documented exception ("if `.continuity/` itself is unwritable, this specific log write may also fail silently"); restored to 755 | PASS |
| 4.1 | `schema_version` one below current (`1.0`→`0.9`), start a session | Migrated forward, `metadata.json` shows current version, context still loads | `metadata.json` `schema_version` back to `"1.0"` after the session; `additionalContext` still carried the staging block | PASS |
| 4.2 | `schema_version` one above current (`1.0`→`2.0`), start a session | Session starts normally, no continuity (history) context injected, `metadata.json` byte-identical, `unsupported-schema` logged | `RESULT is_error=false`; injected context had the staging instructions only, no `[Continuity context — ...]` label; SHA-256 of `metadata.json` identical before/after; `errors.log`: `... \| migrate \| unsupported-schema \| schema_version 2.0` | PASS |
| 5 | `.gitignore` opt-out (+ `git rm -r --cached` if tracked) | `git status` no longer shows `.continuity/` as trackable; reads/writes continue unchanged | `git status --short --ignored` showed `!! .continuity/`; a follow-up session created `y.txt` and continued updating `.continuity/*.md` normally | PASS |

**All Claude Code rows: PASS.**

## Cursor

Ran with `cursor-agent -p --plugin-dir plugins/continuity --force`, `--output-format
text` for readability (one run used `--output-format stream-json` to inspect the
transcript shape; Cursor's stream-json does not surface `hook_response` events the
way Claude Code's does, so hook evidence for Cursor comes from `.continuity/` file
contents and the model's own answers, not the transcript — noted per the task's own
allowance for Cursor). No explicit `--model` flag; Cursor used its default (`Auto`).

| # | Scenario | Expected | Actual | Result |
|---|---|---|---|---|
| 1 | Session A: decide + leave a task | `.continuity/decisions.md` / `tasks.md` each gain an entry | Both gained one entry (`parse() raises ValueError on bad input` / `Implement input validation for parse()`); `.staged/` empty after; `errors.log` empty | PASS |
| 1 | Session B (fresh, no tools): what was decided? | Answer consistent with recorded decision + task | "raises `ValueError`... EAFP... callers can't silently ignore bad data" / "Implement input validation for `parse()`; the function is still a stub" — matches session A exactly | PASS |
| 3.1 | Missing `.continuity/` | Session starts normally, store recreated | `OK`; `.continuity/{state,tasks,decisions,learnings}.md` + `metadata.json` present after | PASS |
| 3.2 | Corrupted `decisions.md` | Starts normally; `corrupted` logged | `OK`; `errors.log`: `... \| read-decisions \| corrupted \| no title and no entries` | PASS |
| 3.3 | Unreadable `state.md` | Starts normally; `unreadable` logged; chmod restored | `OK`; `errors.log`: `... \| read-state \| unreadable \| PermissionError`; restored to 644 | PASS |
| 3.4 | Write failure (`chmod 000 .continuity/`) + edit | Turn completes normally; `errors.log` write-failed or silent per exception | `OK`; no `errors.log` created (matches documented exception); `x.txt` created; restored to 755 | PASS |
| 4.1 | Schema one below (`0.9`) | Migrated to current, session loads | `metadata.json` `schema_version` back to `"1.0"` | PASS |
| 4.2 | Schema one above (`2.0`) | Starts normally, no history context, metadata byte-identical, `unsupported-schema` logged | `OK`; SHA-256 identical before/after; `errors.log`: `... \| migrate \| unsupported-schema \| schema_version 2.0` | PASS |
| 5 | Git opt-out | Untrackable afterward; reads/writes continue | `git status --short --ignored` → `!! .continuity/`; follow-up session created `y.txt` and updated `.continuity/*.md` | PASS |

**All Cursor rows: PASS.**

### Cursor worker-daemon note (not a failure, recorded per the brief)

`ps -ef | grep cursor-agent` during this run showed the same pre-existing
`cursor-agent worker` daemon verification.md flagged (`--worker-dir
~/.cursor/plugins/cache/njagents/bug-triage-agent/...`), plus one `worker-server`
child process spawned per `-p` invocation in this run. None of the 9 Cursor sessions
above showed corrupted or foreign-plugin environment values in their outcomes (we
only inspected `.continuity/` file contents and model answers, not env vars, so this
is not a re-confirmation of verification.md's `_env` contamination finding — just a
note that the same daemon is still present and still worth knowing about before any
future env-sensitive Cursor recording).

## Codex — NOT OBTAINED (all rows)

**No live Codex hook payload could be exercised in this environment.** Two `codex
exec` attempts were made (both in a fresh scratch repo, `--sandbox workspace-write
--skip-git-repo-check`, no interactive prompt, no `--dangerously-bypass-hook-trust`
per the controller's instruction not to use it):

1. Default model (`gpt-5.6-terra`, this account's configured default):
   ```
   ERROR: You've hit your usage limit. Upgrade to Plus to continue using Codex
   (https://chatgpt.com/explore/plus), or try again at Oct 26th, 2026 2:56 PM.
   ```
2. Retried with `-m gpt-5-mini`:
   ```
   ERROR: {"type":"error","status":400,"error":{"type":"invalid_request_error",
   "message":"The 'gpt-5-mini' model is not supported when using Codex with a
   ChatGPT account."}}
   ```

Both failed before issuing a single model turn, so no tool call — and therefore no
`PostToolUse` hook invocation — ever occurred. This is a different failure mode than
verification.md's Task 1 blocker (that was model-rejection only; this run additionally
hit an account-level usage cap that persists until 2026-10-26), but the net effect is
the same: **no Codex session in this environment can reach a point where plugin hooks
run**, so V5's "say so, mark not obtained rather than passed" applies to every
Codex row.

The plugin itself was confirmed correctly installed and pointed at this exact branch
before attempting any session — not part of the live-hook evidence, but ruling out
"wrong install" as the cause:

```
$ codex plugin list --json | jq '.installed[] | select(.pluginId=="continuity@continuity")'
{
  "pluginId": "continuity@continuity",
  "version": "0.1.2",
  "installed": true,
  "enabled": true,
  "marketplaceSource": {"sourceType": "git", "source": "https://github.com/navjyotnishant/continuity.git"}
}
$ cat ~/.codex/.tmp/marketplaces/continuity/.git/HEAD
ref: refs/heads/feat/multi-agent
$ git -C ~/.codex/.tmp/marketplaces/continuity log --oneline -1
f5995a4 docs: install per coding agent, Desktop unsupported, constitution 1.1.0 (CONTINUI-61)
```

| # | Scenario | Expected | Actual | Result |
|---|---|---|---|---|
| 1 | Session A + B (decide/recall) | — | Could not run any `codex exec` turn (usage limit + model rejection, see above) | **NOT OBTAINED** |
| 3.1–3.4 | Store-breakage cases | — | Same blocker; no session reached a hook | **NOT OBTAINED** |
| 4.1–4.2 | Schema compatibility | — | Same blocker | **NOT OBTAINED** |
| 5 | Git opt-out | — | Same blocker | **NOT OBTAINED** |

### `apply_patch` fixture-shape check (read-only, no fixture/code/test edits)

Per the task's ask, `~/.codex/sessions/**/*.jsonl` (pre-existing rollout logs,
read-only, none from this task's own runs since none completed a turn) was searched
for real `apply_patch` invocations. Several were found, e.g.:

```json
{"type": "response_item", "payload": {"type": "custom_tool_call", "status": "completed",
 "call_id": "call_oLRPTso3WrzQcpyyPuIG3ikz", "name": "apply_patch",
 "input": "*** Begin Patch\n*** Update File: /Users/.../vite.config.js\n@@\n ...\n*** End Patch\n"}}
```

This is the **model's own turn-transcript record** of the tool call (from
`response_item`/`custom_tool_call`), not a recording of the plugin's `PostToolUse`
hook stdin payload — those are two different data paths and Codex does not log the
latter anywhere on disk. So this does **not** fully confirm or refute
`tests/fixtures/agents/codex/PostToolUse-apply_patch.json`'s exact hook-payload
shape (`tool_input.command` as a string). It does independently corroborate two of
that fixture's underlying assumptions, both matching:

- The header lines are exactly `*** Begin Patch`, `*** Add File:`, `*** Update
  File:`, `*** Delete File:`, `*** End Patch` — matching `patch_paths`'s expected
  header set and verification.md's earlier static-binary confirmation.
- The patch text itself (the `input` field, which is the same value that becomes
  the tool call's argument the hook would eventually see as `tool_input.command`)
  is a **plain string**, never a list — consistent with the fixture's string-shaped
  `tool_input.command` and with `test_command_given_as_list_is_joined` in
  `tests/test_agents.py` only needing to handle the list form defensively, not as
  the observed default.

No fixture, code, or test file was edited based on this — it is reported as
corroborating-but-not-conclusive evidence only, per the instruction not to touch any
of those files in this task.

## Deviations

| # | Severity | Finding | Evidence | Suggested fix |
|---|---|---|---|---|
| D1 | **High** | Codex cannot be live-verified at all in this environment: the account's default model is usage-capped until 2026-10-26, and every fallback model tried is rejected outright for a ChatGPT-account auth type. This blocks not just this task but any future live Codex verification on this machine before that date. | `ERROR: You've hit your usage limit... try again at Oct 26th, 2026`; `gpt-5-mini` rejected with `"is not supported when using Codex with a ChatGPT account"` | Re-run Task 7's Codex rows after 2026-10-26 (or from an API-key-backed Codex account instead of a ChatGPT-account login, if one becomes available), and update this file in place rather than re-deriving it. |
| D2 | Medium | Cursor's stream-json output format does not expose `hook_response`/hook-event entries the way Claude Code's does, so a Cursor session's injected `additional_context` cannot be directly captured from the CLI transcript — only inferred from the model's downstream behavior and `.continuity/` file state. | `s1-stream.jsonl` (this run) contains only `system/init`, `user`, `thinking`, `assistant`, `result` event types — no hook events at all | If a future task needs byte-exact Cursor injected-context evidence, capture it via a throwaway recorder plugin (as Task 1's spike did) rather than relying on `cursor-agent`'s own transcript output. |
| D3 | Low | The pre-existing `cursor-agent worker` background daemon (`--worker-dir ~/.cursor/plugins/cache/njagents/bug-triage-agent/...`, flagged in verification.md's "Fix round 1") is still running on this machine and still spawns one `worker-server` child per `-p` invocation. It caused no observed failure in this run (only `.continuity/` file contents and model answers were inspected, not env vars), but remains a latent risk for any future env-sensitive Cursor recording. | `ps -ef \| grep cursor-agent` during this run shows the same worker plus 7 `worker-server` children, one per Cursor session started | No action needed for this task. A future Cursor env-recording task should expect the same contamination verification.md already documented and apply the same fixture-scrubbing fallback. |

Per the brief, these are recorded here only; the controller files them as Jira tasks
under the Epic before this task is counted done — none were filed by this run.
