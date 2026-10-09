# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- The end-of-turn request for a note now also fires after work done in the shell: files
  written with `>`, `sed -i`, `tee`, `mv` and the like, and commits made as
  `git -c k=v commit` or `git -C dir commit`. Before, only a literal `git commit` or an
  editor-tool edit counted.
- A read-only git command such as `git status` no longer counts as an edit just because the
  repo has uncommitted changes.

## [0.2.4] - 2026-10-09

### Fixed

- Entries saved in the same run now recall newest first. Before, the oldest came first
  and the recall limit cut off the newest.
- Open tasks now rank by when they were last updated, not just created.
- An empty state note no longer refreshes the date on a state that did not change.

### Added

- A task note can now carry `status: active`, `status: blocked` or `status: done`, and
  a later note with the same title updates that task in place, so a finished task is
  marked done instead of staying active forever.
- A new `state` note replaces the project's current state (`state.md`): a short
  summary plus constraints. Nothing used to write that file.

### Changed

- The end-of-turn request for a note now says a code comment or the diff is not a
  record, so agents stop skipping a decision just because its reason is written in
  a comment.

## [0.2.3] - 2026-10-08

### Fixed

- A note the agent saves with a shell command (as Codex does) is now saved at the end
  of the turn, not left waiting for a later git command.

## [0.2.2] - 2026-10-08

### Added

- Continuity now asks for a note at the end of a turn instead of hoping one
  gets written. When a turn changed files and nothing was staged, a new Stop
  hook asks the agent once to stage a short summary (a decision, learning,
  task or handoff), or nothing if nothing qualifies. Turns without changes are
  untouched, and it never asks twice in one turn. Works in Claude Code and
  Codex (same turn) and in Cursor (as an automatic follow-up message).

### Changed

- Claude Desktop (Cowork) is now documented as limited to the Cowork workspace
  rather than unsupported. Its hooks do run, but the store lives in the cloud
  container, not your connected folder, and is lost when the container resets
  between sessions.

## [0.2.1] - 2026-09-28

### Changed

- Continuity is now licensed under the Apache License 2.0 (previously MIT).
- The Claude Code plugin listing now describes Continuity as memory for coding
  agents, matching the Codex and Cursor listings.
- The install guide explains how to update in each coding agent and how to check
  the installed version. It also covers what to do when an update keeps
  installing an old version: the marketplace was added pinned to a branch, so
  remove it and add it again.

## [0.2.0] - 2026-09-27

### Added

- Continuity now installs and runs in **Cursor** as well as Claude Code, from
  the same GitHub marketplace. Both are live-verified: each recalls at session
  start, captures after meaningful edits and commits, and flushes at session
  end.
- Continuity now also installs in **Codex**, shipped as **beta**: it is built
  and unit-tested but not yet verified in a live Codex session (tracked in
  CONTINUI-64), so treat its recall/capture behavior as unconfirmed until a
  later patch release verifies it live.
- A `continuity-checkpoint` skill, for Codex, which loads skills but not
  commands.

### Changed

- Install docs are now per coding agent. Claude Desktop (Cowork) is documented
  as unsupported, because it does not run plugin hooks.
- The plugin now lives under `plugins/continuity/`. Existing Claude Code
  installs pick this up automatically on the next marketplace update, with
  the same plugin id.

## [0.1.2] - 2026-09-27

### Fixed

- The plugin no longer reports "failed to load". Its manifest named
  `hooks/hooks.json`, which Claude Code already loads automatically, so the
  hooks were registered twice. (CONTINUI-48)
- SessionStart's recording instructions and `/continuity-checkpoint` now give
  the project's absolute `.continuity/.staged/` path. The bare relative path
  could be resolved against Claude Code's own memory directory instead, and
  notes never reached the project store. (CONTINUI-49)
- Entry titles no longer repeat their kind: a note headed
  `# Decision: X` is recorded as `Decision: X`, not
  `Decision: Decision: X`. (CONTINUI-50)
- A durable file overwritten with text that has neither a title nor any entry
  is now logged as `corrupted` in `errors.log`, instead of being read silently
  as empty. (CONTINUI-51)
- A newly created store records the installed plugin's version in
  `metadata.json` instead of a hardcoded `0.1.0`. (CONTINUI-52)
- `docs/install.md` names the secret scanner's real file,
  `lib/secret_scan.py`. (CONTINUI-53)

## [0.1.1] - 2026-09-27

### Fixed

- SessionStart now always tells Claude how and when to record something into
  `.continuity/` — the path, timing, and kind of a staged note — instead of
  leaving the Content Channel convention undocumented outside a spec file no
  session reads at runtime. Without this, nothing was ever staged and the
  write path never fired on its own. (CONTINUI-47)
- The background writer now targets the repository the edited file actually
  belongs to, not the session's own working directory. A session's `cwd` and
  the file a tool call touches can be different repositories entirely, and
  notes were previously written into the wrong project's store in that case.
  (CONTINUI-47)
- `tests/test_atomic_write.py` no longer uses a `pathlib.Path.read_text()`
  keyword argument (`newline`) that only exists on Python 3.13+, which broke
  the suite on this project's stated Python 3.9+ minimum. (CONTINUI-47)
- `tests/test_migrate.py`'s write-denied migration test no longer asserts an
  `errors.log` entry in a scenario where the log's own directory is also
  unwritable, so the append is expected to fail silently by design.
  (CONTINUI-45)

## [0.1.0] - 2026-09-22

### Added

- Initial release: cross-session project memory for Claude Code. Persists
  project-scoped state, decisions, tasks, and learnings under `.continuity/`
  as plain Markdown/JSON, loads a bounded, provenance-labeled subset at
  `SessionStart`, and writes asynchronously — detached from the interactive
  turn — on meaningful-change triggers (`PostToolUse`, `SessionEnd`, and the
  `/continuity-checkpoint` command).
- Fails open on every documented failure mode: a missing, corrupted, or
  unwritable store never blocks or crashes a session — only `errors.log`
  records it.
- A local secret scanner runs over every staged note before it is written to
  a durable file.
- Retention pruning for old session-handoff files and stale lock/temp debris.

[Unreleased]: https://github.com/navjyotnishant/continuity/compare/v0.2.4...HEAD
[0.2.4]: https://github.com/navjyotnishant/continuity/compare/v0.2.3...v0.2.4
[0.2.3]: https://github.com/navjyotnishant/continuity/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/navjyotnishant/continuity/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/navjyotnishant/continuity/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/navjyotnishant/continuity/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/navjyotnishant/continuity/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/navjyotnishant/continuity/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/navjyotnishant/continuity/releases/tag/v0.1.0
