# Continuity

Cross-session memory for Claude Code — as a plugin, not a service.

Every new Claude Code session starts with no memory of the last one, so a
developer re-explains the same decisions, constraints, and open tasks over
and over. Continuity fixes that by persisting a project's important context
— decisions made, current state, active tasks, constraints, and learnings —
to plain text files, and loading a small, relevant slice of it back in at the
start of the next session. Full rationale: [`docs/intent/continuity.md`](docs/intent/continuity.md).

**Status**: repository skeleton laid out, implementation in progress. This
repository holds the intent doc, the full feature specification, and the
implementation plan (see [`specs/001-continuity/`](specs/001-continuity/)).
`lib/common.sh` (path resolution, fail-open logging, metadata defaults) and
the `tests/run_tests.sh` harness exist and pass; the rest of the plugin's
scripts (`hooks/`, `commands/`, the remaining `lib/` modules, `templates/`,
`.claude-plugin/`) are scaffolded as empty directories awaiting the
implementation phases in
[`specs/001-continuity/tasks.md`](specs/001-continuity/tasks.md).

## Why a plugin, not a service

Continuity ships strictly as a Claude Code plugin distributed via a
GitHub-hosted marketplace — no separate server, no database installation, no
cloud dependency, and no Go, Python, Node, or other standalone runtime. The
entire implementation is POSIX-compatible Bash plus coreutils already present
wherever Claude Code's own hooks run. See
[`specs/001-continuity/plan.md`](specs/001-continuity/plan.md) → Technical
Context for the full constraint set and why each alternative (Python, an
embedded database, `flock`) was rejected.

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
.claude-plugin/   Plugin manifest + marketplace listing (not yet populated)
hooks/            SessionStart / PostToolUse / SessionEnd hook scripts
commands/         Slash commands (e.g. /continuity-checkpoint)
lib/              Shared logic: locking, atomic writes, secret scan,
                  context selection, schema migration, retention
templates/        Seed content for a first-ever .continuity/ store
tests/            Plain-Bash assertion scripts — no test framework dependency
scripts/hooks/    This repo's own git hooks (secret-scan pre-commit)
docs/             Intent doc and install/usage docs
specs/            Feature spec, implementation plan, and tasks (spec-kit)
```

`hooks/`, `commands/`, `templates/`, and `.claude-plugin/` are currently
empty directories (tracked via `.gitkeep`); `lib/` holds `common.sh` with
the rest of its modules still to come — see
[`specs/001-continuity/tasks.md`](specs/001-continuity/tasks.md) for the
task-by-task build order.

## Installing (once implemented)

Continuity will install like any other Claude Code plugin, from this repo's
marketplace listing (`.claude-plugin/marketplace.json`). Install
instructions will live in `docs/install.md` once the plugin manifest exists,
including the documented `.gitignore` opt-out for teams that want
`.continuity/` to stay local-only rather than git-tracked (`.continuity/` is
git-tracked by default — see spec.md Q1/FR-020).

## Development

```bash
bash tests/run_tests.sh
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
