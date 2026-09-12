# Contributing to Continuity

Continuity is a Claude Code plugin written entirely in POSIX-compatible Bash
plus standard coreutils — no Go, Python, Node, or package manager (see
`specs/001-continuity/plan.md` → Technical Context). Keep that constraint in
mind before proposing a dependency; it is a hard requirement, not a style
preference.

## Before you start

1. Read `docs/intent/continuity.md` and `specs/001-continuity/spec.md` — they
   ground every design decision and answer most "why not X" questions.
2. Feature work is cut from `develop` and merges back via a reviewed pull
   request; nothing pushes directly to `main` or `develop`
   (`.specify/memory/constitution.md`, Principles I and V).
3. A plan is written and reviewed before implementation starts (Principle II).

## Running the tests

```bash
bash tests/run_tests.sh
```

The suite is plain Bash assertions (`tests/test_*.sh`) — no test framework is
installed or required (see plan.md's rejection of `bats-core`).

## Style

- Target bash 3.2 (macOS's stock version) and any Linux bash ≥ 4 —
  `specs/001-continuity/plan.md` → Technical Context.
- Every hook script must fail open: wrap the real work, log failures locally
  to `.continuity/errors.log`, and never let a Continuity error surface as a
  blocking error to the developer (FR-012).
- Never introduce a runtime dependency (no Python/Node/Go), a database, a
  server process, or a network call — these are constitution-level
  constraints, not implementation preferences.

## Submitting a change

Open a pull request against `develop` describing what changed and why, and
reference the relevant `FR-`/`SC-` requirement ID from `spec.md` when the
change implements or affects one.
