# CLAUDE.md

Agent-legibility notes for working in this repository. Not a governance
document — see `.specify/memory/constitution.md` for the binding rules this
project is held to, and `specs/001-continuity/plan.md` for the full design.

## What this repo is

Continuity: a Claude Code plugin, written entirely in POSIX-compatible Bash
plus coreutils, that gives a Claude Code session memory of a project's prior
sessions via plain Markdown/text files under `.continuity/`. No Go, Python,
Node, database, server, or cloud dependency — see
`docs/intent/continuity.md` for why.

## Layout

```
.claude-plugin/   Plugin manifest + marketplace listing
hooks/            SessionStart / PostToolUse / SessionEnd hook scripts
commands/         Slash commands (e.g. /continuity-checkpoint)
lib/              Shared logic: locking, atomic writes, secret scan, context
                  selection, migration, retention
templates/        Seed content for a first-ever .continuity/ store
tests/            Plain-Bash assertion scripts (no test framework)
docs/             Intent doc + install/usage docs
specs/            Feature spec, plan, tasks (spec-kit workflow)
```

`hooks/` and `commands/` are the plugin's event surface; everything reusable
lives in `lib/` so each hook script stays a thin, fast dispatcher.

## Build & test

No build step (plain shell scripts, nothing to compile).

```bash
bash tests/run_tests.sh
```

## Conventions

- Target bash 3.2 (macOS stock) and Linux bash ≥ 4 — no bashisms newer than
  that.
- Every hook fails open: wrap the real work, log to `.continuity/errors.log`
  on error, never block or crash the interactive session (FR-012).
- Memory writes are fire-and-forget detached background processes, never
  synchronous with the triggering hook (FR-010).
- Don't add a dependency — the entire point of this project is having none.

## Where the answers already are

Before re-deriving a design decision, check `specs/001-continuity/spec.md`'s
Open Questions (Q1–Q10) and `plan.md`'s "What was rejected, and why?" —
most "why not X" questions are already answered there.
