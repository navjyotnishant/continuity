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

Run the writer. `<plugin>` is this plugin's own install location: the
directory two levels above this `SKILL.md` (i.e. `SKILL.md`'s directory,
then up two more levels). A shared hook/skill worker's environment can carry
*another* plugin's `CLAUDE_PLUGIN_ROOT` or `PLUGIN_ROOT`, so only fall back to
those environment variables if this skill's own path cannot be determined.
Before running the command, confirm `<plugin>/lib/write_memory.py` exists —
if it does not, the resolved `<plugin>` is wrong; fall back to the
environment variables (or report the failure if neither resolves).

```bash
python3 "<plugin>/lib/write_memory.py" "<root>" explicit-checkpoint
```

## Step 4: report

Relay the writer's one-line result: either `Checkpoint written to …` plus one line per
note captured, or exactly `Nothing new to checkpoint`. Never commit `.continuity/`
with git; that is the developer's decision.
