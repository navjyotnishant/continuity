# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/navjyotnishant/continuity/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/navjyotnishant/continuity/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/navjyotnishant/continuity/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/navjyotnishant/continuity/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/navjyotnishant/continuity/releases/tag/v0.1.0
