# Continuity

Cross-session memory for Claude Code — as a plugin, not a service.

Every new Claude Code session starts with no memory of the last one, so a
developer re-explains the same decisions, constraints, and open tasks over
and over. Continuity fixes that by persisting a project's important context
— decisions made, current state, active tasks, constraints, and learnings —
to plain text files, and loading a small, relevant slice of it back in at the
start of the next session. Full rationale: [`docs/intent/continuity.md`](docs/intent/continuity.md).

**Status**: working plugin, version 0.1.2. The hooks, the
`/continuity-checkpoint` command, the store logic in `lib/` and the seed
templates are all implemented, every task in
[`specs/001-continuity/tasks.md`](specs/001-continuity/tasks.md) is done,
and the suite (`python3 tests/run_tests.py`, plus the shell suite) runs in
CI on every pull request. Design and requirements live in
[`specs/001-continuity/`](specs/001-continuity/).

## Why a plugin, not a service

Continuity ships strictly as a Claude Code plugin distributed via a
GitHub-hosted marketplace — no separate server, no database installation, no
cloud dependency, and no Go, Node, or other standalone runtime. The entire
implementation is Python 3.9+ standard library only — no third-party
packages, no `pip install` step, no `requirements.txt`/`pyproject.toml`.
Python is not a new runtime this plugin introduces: it is already required to
run Claude Code hooks in this environment. See
[`specs/001-continuity/plan.md`](specs/001-continuity/plan.md) → Technical
Context for the full constraint set and why each alternative (an embedded
database, `flock`, `pytest`) was rejected.

## How it works

- **Storage**: project-scoped Markdown files under `.continuity/` at the
  project root (`state.md`, `decisions.md`, `tasks.md`, `learnings.md`),
  plus `metadata.json` and a `sessions/` handoff log. No database engine.
- **Session start** (`hooks/session-start.py`): loads a bounded,
  provenance-labeled subset of the store as injected context, marked as
  recorded by a prior session rather than a live instruction. Selection is
  plain per-section line budgets, with `active` and `blocked` tasks
  preferred over `done` ones.
- **Staging notes**: the session is told where to drop notes worth keeping,
  as `.continuity/.staged/<kind>-<timestamp>-<pid>.md`, where `<kind>` is
  `decision`, `task`, `learning` or `handoff`. Continuity never composes
  content itself and never calls an LLM; it consolidates what was staged.
- **Writes** (`hooks/capture-trigger.py`, `hooks/session-end.py`): a
  meaningful change (an edit, a git diff or commit) or `SessionEnd` launches
  `lib/write_memory.py` as a detached background process, so the triggering
  hook returns immediately. The writer secret-scans every line, appends each
  note to its durable file, writes one handoff to `sessions/`, and prunes
  what is past its retention window. Notes land in the repository of the
  file that was edited, not the session's working directory.
- **On demand**: `/continuity-checkpoint` stages and consolidates right now,
  synchronously, instead of waiting for the next trigger.
- **Concurrency**: an `os.mkdir()` store lock, broken if a crashed writer
  leaves it stale, and atomic temp-file-and-rename writes.
- **Failure handling**: every read or write fails open. On any error
  (missing directory, corrupted file, a store schema it does not
  understand) the operation is skipped and logged to
  `.continuity/errors.log`, and Claude Code carries on as if Continuity were
  not installed.

The full requirement set (FR-001 to FR-020) and the resolved open questions
are in [`specs/001-continuity/spec.md`](specs/001-continuity/spec.md).

## Install

Inside Claude Code:

```text
/plugin marketplace add navjyotnishant/continuity
/plugin install continuity@continuity
```

Needs `python3` (3.9 or newer) on `PATH`, which Claude Code hooks already
rely on. In a project that has no store yet, Continuity creates
`.continuity/` from `templates/`.

`.continuity/` is git-tracked by default, so a teammate's session inherits
the same context. [`docs/install.md`](docs/install.md) covers opting it out
of version control, what the secret scan does and does not catch, and the
`retention_days` and `git_tracked` settings in `metadata.json`.

## Repository layout

```
.claude-plugin/   Plugin manifest and marketplace listing
hooks/            SessionStart / PostToolUse / SessionEnd hooks + hooks.json
commands/         /continuity-checkpoint
lib/              Store logic: selection, writer, locking, atomic writes,
                  secret scan, schema migration, retention (the .sh files
                  are shell twins exercised by the shell test suite)
templates/        Seed content for a first-ever .continuity/ store
tests/            Stdlib unittest suite (tests/run_tests.py) and shell
                  suite (tests/run_tests.sh)
scripts/hooks/    This repo's own git hooks (secret-scan pre-commit)
docs/             Intent doc and install notes
specs/            Feature spec, implementation plan and tasks (spec-kit)
```

## Development

```bash
python3 tests/run_tests.py
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
