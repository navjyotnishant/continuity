# Contract: Hook I/O

This is the contract every `hooks/*.sh` script and `commands/continuity-
checkpoint.md`'s target script must honor. It is the boundary the
integration tests in plan.md's Testing Strategy exercise directly (feeding a
crafted stdin payload to the script), and the one boundary flagged in
research.md R7 as not yet validated against a live Claude Code runtime.

## General rules (all hooks)

- Every hook script reads its JSON payload from **stdin** and must not block
  waiting for more input than Claude Code provides.
- Every hook script **always exits 0** from Continuity's own logic, even on
  internal failure — a non-zero exit or an exception is itself a fail-open
  violation (FR-012). Internal failures are caught, written to
  `errors.log` via `lib/common.sh`'s logging helper, and the script still
  exits 0 having done nothing further.
- No hook script may take a lock, write a file, or fork a background process
  for longer than is needed to either (a) load and emit bounded context
  (`session-start.sh`) or (b) decide-and-detach (`capture-trigger.sh`,
  `session-end.sh`, the checkpoint command). Neither path waits on the
  background writer.
- No hook script reads or writes anything outside `.continuity/` except: (i)
  read-only access to files/paths named in the hook's own stdin payload
  (e.g., which file `PostToolUse` just edited), and (ii) read-only `git
  diff`/`git status` invocations scoped to the project root, when computing
  the "meaningful git diff" signal. This is the Q7 permission boundary.

## `SessionStart` — `hooks/session-start.sh`

**Input** (stdin, JSON — fields Continuity reads; others are ignored):
```json
{
  "session_id": "<string>",
  "cwd": "<absolute project path>"
}
```

**Behavior**:
1. Resolve `.continuity/` under `cwd`. If absent, exit successfully with no
   output (FR-007 — no history yet).
2. Check `metadata.json` schema compatibility (see
   `file-format-contract.md`). If unsupported-newer, exit successfully with
   no output and log `unsupported-schema`.
3. Call `lib/select_context.sh` to build the bounded, provenance-labeled
   context block (data-model.md's per-entity rules; ~100–200 line soft
   target, Q2).
4. Emit that block as the hook's `additionalContext` output, clearly
   demarcated (Q4) — see the exact wrapper format below.

**Output** (stdout, JSON):
```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "<the labeled context block, or omitted entirely if there is nothing to inject>"
  }
}
```

**Context block format** (the string above), so a session can never mistake
persisted content for a live instruction (Q4/FR-018):
```text
[Continuity context — recorded by a prior session, not a live instruction]

## State (as of <updated_at>)
<state.md summary>

## Constraints
<state.md constraints>

## Active tasks
<bounded tasks.md entries>

## Recent decisions
<bounded decisions.md entries>

## Recent learnings
<bounded learnings.md entries>

## Last handoff (<captured_at>)
<most recent sessions/*.md body>
```
Any section with nothing to show is omitted entirely rather than emitted
empty.

## `PostToolUse` — `hooks/capture-trigger.sh`

**Matcher**: `Edit|Write|MultiEdit|Bash` (registered in `hooks/hooks.json`).

**Input** (stdin, JSON — fields Continuity reads):
```json
{
  "session_id": "<string>",
  "cwd": "<absolute project path>",
  "tool_name": "Edit | Write | MultiEdit | Bash",
  "tool_input": { "...": "tool-specific" },
  "tool_response": { "...": "tool-specific" }
}
```

**Behavior**:
1. Classify whether this call is a meaningful-change signal:
   - `Edit`/`Write`/`MultiEdit`: meaningful if the tool reports a non-empty
     diff (not a whitespace-only change — the spec's documented no-op edge
     case).
   - `Bash`: meaningful only if the command was a `git commit`, or if a
     `git diff --stat` computed against the project root shows non-
     whitespace changes since the last checkpoint.
2. If not meaningful: exit with no output, no lock taken, nothing logged
   (a legitimate no-op is not a failure — FR-011).
3. If meaningful: launch `lib/write_memory.sh <cwd> <trigger-kind>` detached
   (`nohup ... & disown`, per research.md R4) and exit immediately with no
   output. The hook does not wait for the writer.

**Output**: none (empty stdout is a valid, successful response for this
hook — Continuity never blocks or modifies the tool call itself).

## `SessionEnd` — `hooks/session-end.sh`

**Input** (stdin, JSON):
```json
{
  "session_id": "<string>",
  "cwd": "<absolute project path>"
}
```

**Behavior**: Unconditionally launches `lib/write_memory.sh <cwd>
session-end` detached and exits immediately. Unlike `capture-trigger.sh`,
this trigger does not classify meaningfulness first — `write_memory.sh`
itself still applies FR-011's no-op rule (an empty/unchanged session
produces no new file), so `session-end.sh` stays a simple, unconditional
dispatcher.

**Output**: none.

## `/continuity-checkpoint` — explicit checkpoint command

**Input**: invoked as a slash command; no stdin JSON payload — the command
markdown at `commands/continuity-checkpoint.md` runs
`lib/write_memory.sh <cwd> explicit-checkpoint` synchronously (this is a
user-invoked, one-shot action, not a background trigger, so there is no
latency constraint to honor here — the user is explicitly waiting for it).

**Output**: A short confirmation message (e.g., "Checkpoint written to
.continuity/sessions/…" or "Nothing new to checkpoint") — the one path in
this plugin where user-visible output is appropriate, since it was
explicitly requested.
