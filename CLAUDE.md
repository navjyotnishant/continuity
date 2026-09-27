# CLAUDE.md

Agent-legibility notes for working in this repository. Not a governance
document — see `.specify/memory/constitution.md` for the binding rules this
project is held to, and `specs/001-continuity/plan.md` for the full design.

## What this repo is

Continuity: a plugin for Claude Code, Codex and Cursor, written entirely in
Python 3.9+ standard library (no third-party packages), that gives a coding
agent session memory of a project's prior sessions via plain Markdown/text
files under `.continuity/`. No Go, Node, database, server, or cloud
dependency — see `docs/intent/continuity.md` for why.

## Layout

```
.claude-plugin/marketplace.json   Marketplace listing; source points at
                                   plugins/continuity
docs/             Intent doc + install/usage docs
specs/            Feature spec, plan, tasks (spec-kit workflow)
plugins/continuity/   The plugin root — Codex ignores a marketplace plugin
                       whose source is the repo root, so the plugin lives in
                       a real subfolder (CONTINUI-59):
  .claude-plugin/plugin.json   Plugin manifest
  .codex-plugin/    Codex manifest
  .cursor-plugin/   Cursor manifest
  hooks/            SessionStart / PostToolUse / SessionEnd hook scripts
  commands/         Slash commands (e.g. /continuity-checkpoint)
  skills/           checkpoint skill (Codex loads skills, not commands)
  lib/              Shared logic: locking, atomic writes, secret scan,
                    context selection, migration, retention, lib/agents.py
                    (detects the coding agent and normalizes its hook
                    payloads)
  templates/        Seed content for a first-ever .continuity/ store
  tests/            Stdlib `unittest` tests, run via tests/run_tests.py (no
                    third-party test framework)
```

`hooks/` and `commands/` are the plugin's event surface; everything reusable
lives in `lib/` so each hook script stays a thin, fast dispatcher.

## Build & test

No build step (interpreted Python, nothing to compile).

```bash
cd plugins/continuity
python3 tests/run_tests.py   # unittest suite
bash tests/run_tests.sh      # shell tests (manifest, docs, opt-out); CI runs both
```

## Conventions

- Target Python 3.9+ stdlib only, across macOS, Linux, and native Windows —
  no API newer than 3.9, no third-party import, ever.
- Every hook fails open: wrap the real work, log to `.continuity/errors.log`
  on error, never block or crash the interactive session (FR-012).
- Memory writes are fire-and-forget detached background processes, never
  synchronous with the triggering hook (FR-010).
- Don't add a dependency — the entire point of this project is having none.

## Where the answers already are

Before re-deriving a design decision, check `specs/001-continuity/spec.md`'s
Open Questions (Q1–Q10) and `plan.md`'s "What was rejected, and why?" —
most "why not X" questions are already answered there.
