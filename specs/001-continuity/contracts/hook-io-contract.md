# Contract: Hook I/O

This is the contract every `hooks/*.py` script and `commands/continuity-
checkpoint.md`'s target script must honor. It is the boundary the
integration tests in plan.md's Testing Strategy exercise directly (feeding a
crafted stdin payload to the script), and the one boundary flagged in
research.md R7 as not yet validated against a live Claude Code runtime.

## General rules (all hooks)

- Every hook script reads its JSON payload from **stdin** and must not block
  waiting for more input than Claude Code provides.
- Every hook script **always exits 0** from Continuity's own logic, even on
  internal failure — a non-zero exit or an uncaught exception is itself a
  fail-open violation (FR-012). Internal failures are caught, written to
  `errors.log` via `lib/common.py`'s logging helper, and the script still
  exits 0 having done nothing further.
- No hook script may take a lock, write a file, or spawn a background
  process for longer than is needed to either (a) load and emit bounded
  context (`session-start.py`) or (b) decide-and-detach (`capture-
  trigger.py`, `session-end.py`, the checkpoint command). Neither path waits
  on the
  background writer.
- No hook script reads or writes anything outside `.continuity/` except: (i)
  read-only access to files/paths named in the hook's own stdin payload
  (e.g., which file `PostToolUse` just edited), and (ii) read-only `git
  diff`/`git status` invocations scoped to the project root, when computing
  the "meaningful git diff" signal. This is the Q7 permission boundary.

## `SessionStart` — `hooks/session-start.py`

**Input** (stdin, JSON — fields Continuity reads; others are ignored):
```json
{
  "session_id": "<string>",
  "cwd": "<absolute project path>"
}
```

**Behavior**:
1. Resolve `.continuity/` under `cwd`. If absent, seed the store from
   `templates/*.tmpl` (CONTINUI-46 — a fresh install gets its store on the
   first session rather than on the first checkpoint) and exit successfully
   with no output (FR-007 — no history yet). Seeding is best-effort: a store
   that cannot be created is logged and the session proceeds unchanged
   (FR-012).
2. Check `metadata.json` schema compatibility (see
   `file-format-contract.md`). If unsupported-newer, exit successfully with
   no output and log `unsupported-schema`.
3. Call `lib/select_context.py` to build the bounded, provenance-labeled
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

## Content Channel — staged notes (resolves analyze finding C1)

`write_memory.py` never composes prose; it only consolidates. The
natural-language content of a Decision's rationale, a Learning's body, a
Task's description, or a Handoff's summary is written by Claude directly,
as a file, before any trigger fires:

- **Path**: `.continuity/.staged/<kind>-<UTC-timestamp>-<pid>.md`, where
  `<kind>` is one of `decision`, `task`, `learning`, `handoff`.
- **Format**: plain text/Markdown — exactly the note body Claude already
  composed for the corresponding entry in data-model.md (a Decision Record,
  Task Entry, Learning, or Session Handoff's Body field). No front-matter or
  schema beyond the filename's `<kind>` tag; `write_memory.py` routes on
  that tag alone.
- **Writer**: Claude's own Write tool, run inline in the session — not a
  hook, not a background process, not an LLM call inside `write_memory.py`.
  This is the one piece of composition a shell script cannot do, and it is
  work the session was already doing (recognizing and phrasing the note).
- **Consumer**: `write_memory.py` reads every file under `.staged/`,
  secret-scans and appends each into its matching durable file via
  `atomic_write.py`, and removes the staged file once consumed. A staged
  file left over from a run where no trigger fired simply waits for the
  next `capture-trigger.py` or `SessionEnd` invocation.
- **Fail-open**: a staged file that fails the secret scanner in full, or is
  unreadable/malformed, is dropped and logged to `errors.log` (FR-012);
  `write_memory.py` still exits 0 and still consolidates every other staged
  file it found.

This adds no new hook and no new event: it is a filesystem convention
`/continuity-checkpoint` and (in later phases, as needed) other
Claude-driven call sites use before invoking `write_memory.py`.

## `PostToolUse` — `hooks/capture-trigger.py`

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
3. If meaningful: launch `["python3", "lib/write_memory.py", cwd,
   trigger_kind]` detached (`subprocess.Popen(..., **detach_kwargs)`, per
   research.md R4) and exit immediately with no output. The hook does not
   wait for the writer.

**Output**: none (empty stdout is a valid, successful response for this
hook — Continuity never blocks or modifies the tool call itself).

## `SessionEnd` — `hooks/session-end.py`

**Input** (stdin, JSON):
```json
{
  "session_id": "<string>",
  "cwd": "<absolute project path>"
}
```

**Behavior**: Unconditionally launches `lib/write_memory.py <cwd>
session-end` detached and exits immediately. Unlike `capture-trigger.py`,
this trigger does not classify meaningfulness first — `write_memory.py`
itself still applies FR-011's no-op rule (an empty/unchanged session
produces no new file), so `session-end.py` stays a simple, unconditional
dispatcher.

**Output**: none.

## `/continuity-checkpoint` — explicit checkpoint command

**Input**: invoked as a slash command; no stdin JSON payload. Before
invoking the writer, the command's own logic (run by Claude, per the
Content Channel above) writes a staged note to `.continuity/.staged/` for
whatever is worth capturing right now, then
`commands/continuity-checkpoint.md` runs
`lib/write_memory.py <cwd> explicit-checkpoint` synchronously (this is a
user-invoked, one-shot action, not a background trigger, so there is no
latency constraint to honor here — the user is explicitly waiting for it).
If nothing was staged, `write_memory.py` still runs and reports the
existing "nothing new" no-op (FR-011) — the checkpoint command never skips
invoking it.

**Output**: A short confirmation message (e.g., "Checkpoint written to
.continuity/sessions/…" or "Nothing new to checkpoint") — the one path in
this plugin where user-visible output is appropriate, since it was
explicitly requested.
