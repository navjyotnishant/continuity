---
description: Checkpoint what this session has learned into .continuity/ right now
allowed-tools: Write, Bash(python3:*)
---

# /continuity-checkpoint

Persist the current session's memory-worthy content immediately, instead of
waiting for the next automatic trigger. Unlike every other Continuity path
this one is synchronous — the user asked for it and is waiting, so there is
no latency budget to protect (`contracts/hook-io-contract.md` →
`/continuity-checkpoint`).

## Step 1 — stage what is worth keeping (the Content Channel)

`lib/write_memory.py` consolidates notes; it never composes them. Anything
worth recording has to be written as a file first — this is the Content
Channel defined in `contracts/hook-io-contract.md` and `plan.md`.

Look back over this session and decide what, if anything, a *future* session
would need and could not re-derive from the code. For each such item, use the
Write tool to create one file:

```text
$CLAUDE_PROJECT_DIR/.continuity/.staged/<kind>-<UTC-timestamp>-<pid>.md
```

- `<kind>` is exactly one of `decision`, `task`, `learning`, `handoff`.
- `<UTC-timestamp>` is ISO-8601 basic format with colons and periods
  stripped, e.g. `20260912T140501Z`. `<pid>` is any integer that
  disambiguates two notes written in the same second.
- The file body is plain Markdown: the note as you would explain it to the
  next session. If its first line is a Markdown heading it becomes the
  entry's title; otherwise the whole note is kept as the body and its
  opening words become the title.
- Write a `handoff` note for "where this session left off"; write
  `decision` / `task` / `learning` notes for content that belongs in the
  durable record.

Stage nothing if nothing qualifies. A checkpoint with nothing new is a
legitimate outcome, not a failure (FR-011) — do not invent content to fill
it.

## Step 2 — consolidate

Run the writer synchronously:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/lib/write_memory.py" "$CLAUDE_PROJECT_DIR" explicit-checkpoint
```

It secret-scans every staged line, appends each note into its durable file
(`decisions.md` / `tasks.md` / `learnings.md`), writes one
`.continuity/sessions/<timestamp>-<pid>.md` handoff, and removes the staged
notes it consumed.

## Step 3 — report

Relay the writer's own one-line result to the user, unchanged in meaning:

- `Checkpoint written to …/.continuity/sessions/<file>.md` — say what was
  captured, in one line per note.
- `Nothing new to checkpoint` — say exactly that, and stop. Do not re-run it
  and do not stage something to make it non-empty.

Never run this command with `git`. Continuity writes files; committing them
is the developer's decision.
