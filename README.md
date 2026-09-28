# Continuity

Cross-session memory for coding agents — as a plugin, not a service.

Every new Claude Code session starts with no memory of the last one, so a
developer re-explains the same decisions, constraints, and open tasks over
and over. Continuity fixes that by persisting a project's important context
— decisions made, current state, active tasks, constraints, and learnings —
to plain text files, and loading a small, relevant slice of it back in at the
start of the next session. Full rationale: [`docs/intent/continuity.md`](docs/intent/continuity.md).

**Status**: implemented and released. The plugin lives in
[`plugins/continuity/`](plugins/continuity/); see
[`specs/001-continuity/`](specs/001-continuity/) for the intent doc, full
feature specification, and implementation plan, and
[`specs/002-multi-agent/`](specs/002-multi-agent/) for the Codex/Cursor
support design. For how it all fits together (session flow, agent adapters, the
background writer, the store and failure handling), read
[`docs/architecture.md`](docs/architecture.md).

## Why a plugin, not a service

Continuity ships as a plugin for Claude Code, Codex (beta) and Cursor, distributed via a
GitHub-hosted marketplace — no separate server, no database installation, no
cloud dependency, and no Go, Node, or other standalone runtime. The entire
implementation is Python 3.9+ standard library only — no third-party
packages, no `pip install` step, no `requirements.txt`/`pyproject.toml`.
Python is not a new runtime this plugin introduces: it is already required to
run Claude Code hooks in this environment. See
[`specs/001-continuity/plan.md`](specs/001-continuity/plan.md) → Technical
Context for the full constraint set and why each alternative (an embedded
database, `flock`, `pytest`) was rejected.

## How it works (design)

- **Storage**: project-scoped Markdown/text files under `.continuity/` at the
  project root (`state.md`, `decisions.md`, `tasks.md`, `learnings.md`, plus
  `metadata.json` and a `sessions/` handoff log) — no database engine.
- **Session start**: a `SessionStart` hook loads a bounded (~100–200 line
  soft target), provenance-labeled subset of that store as injected context,
  clearly marked as trusted project context, not as instructions to act on.
- **Memory writes**: triggered by meaningful-change signals (a significant
  file change, a meaningful git diff, a completed task, a recorded decision,
  a test milestone, an explicit checkpoint, or `SessionEnd`) — never on every
  interaction, and never via an LLM call. Writes run as detached,
  fire-and-forget background processes so the triggering hook returns
  immediately.
- **Failure handling**: every read or write fails open — on any error
  (missing directory, corrupted file, write failure) the operation is
  skipped and logged locally to `.continuity/errors.log`, and Claude Code
  continues exactly as if Continuity were not installed.

The full requirement set (FR-001–FR-020), the ten resolved open questions,
and the flagged design tensions are in
[`specs/001-continuity/spec.md`](specs/001-continuity/spec.md).

## Repository layout

```
plugins/continuity/   The plugin root (Codex requires a real subfolder, not
                       the repo root — CONTINUI-59):
  .claude-plugin/   Plugin manifest + marketplace listing
  .codex-plugin/    Codex manifest
  .cursor-plugin/   Cursor manifest
  hooks/            SessionStart / PostToolUse / SessionEnd hook scripts
  commands/         Slash commands (e.g. /continuity-checkpoint)
  skills/           checkpoint skill (Codex loads skills, not commands)
  lib/              Shared logic: locking, atomic writes, secret scan,
                    context selection, schema migration, retention
  templates/        Seed content for a first-ever .continuity/ store
  tests/            Stdlib `unittest` tests, run via tests/run_tests.py — no
                    third-party test framework dependency
scripts/hooks/    This repo's own git hooks (secret-scan pre-commit)
docs/             Intent doc and install/usage docs
specs/            Feature spec, implementation plan, and tasks (spec-kit)
```

## Installing

Continuity installs like any other plugin for Claude Code, Codex (beta) or Cursor, from this repo's
marketplace listing (`.claude-plugin/marketplace.json`). See
[`docs/install.md`](docs/install.md) for per-agent install steps, including the
documented `.gitignore` opt-out for teams that want `.continuity/` to stay
local-only rather than git-tracked (`.continuity/` is git-tracked by default
— see spec.md Q1/FR-020).

## Development

```bash
cd plugins/continuity
python3 tests/run_tests.py
```

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the branching model, style
constraints, and how to enable this repo's secret-scanning pre-commit hook:

```bash
git config core.hooksPath scripts/hooks
```

## Security

No network access, no telemetry, no cloud dependency (FR-019). See
[`SECURITY.md`](SECURITY.md) for how to report a vulnerability. Note the
Concerns section of `spec.md`: persisted content is not currently screened
for secrets beyond a lightweight pattern check before being written to
git-tracked files — read that section before relying on Continuity for a
project with sensitive context.

## License

[MIT](LICENSE). No license was specified in the project's intent or spec
docs at scaffold time — MIT was chosen as the conventional default for an
open-source, GitHub-marketplace-distributed developer tool. **Confirm this
is the intended license** before the first public release; swapping it later
is a one-file change.
