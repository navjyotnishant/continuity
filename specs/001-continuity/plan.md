# Implementation Plan: Continuity

**Branch**: `001-continuity` | **Date**: 2026-09-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-continuity/spec.md`, grounded in
`docs/intent/continuity.md` and `.specify/memory/constitution.md`.

## Summary

Continuity is a Claude Code plugin, distributed via a GitHub-hosted marketplace,
that gives a Claude Code session memory of a project's prior sessions without a
server, a database, a cloud dependency, or a non-shell runtime. It persists
project-scoped context — state, decisions, tasks, learnings, and session
handoffs — as plain Markdown/text files under `.continuity/` at the project
root. A `SessionStart` hook loads a bounded (~100–200 line soft target),
provenance-labeled subset of that store as injected context. Writes are
triggered by meaningful-change signals (file changes, git diffs, task/decision
events, explicit checkpoints, `SessionEnd`) rather than every interaction, and
execute as a detached, fire-and-forget background process so the triggering
hook returns immediately. Every read and write fails open: on any error the
operation is skipped, logged locally, and Claude Code continues unaffected.
The whole implementation is POSIX-compatible Bash plus standard coreutils —
no Go, no Python dependency, no package to install — because that is the only
way to satisfy the constitution's "no standalone runtime for the MVP" and
"feels exactly as fast" constraints without introducing exactly the kind of
new dependency the feature exists to avoid.

## Technical Context

**Language/Version**: POSIX-compatible Bash (targets bash 3.2, macOS's stock
version, and any Linux bash ≥ 4) plus standard coreutils (`mkdir`, `mv`, `date`,
`grep`, `sed`, `wc`, `find`). No Python, Node, or Go.

**Primary Dependencies**: None. Every operation uses a POSIX shell and
coreutils already present wherever Claude Code itself runs. No package
manager, no `pip`/`npm install` step, no vendored library.

**Storage**: Plain Markdown/text files plus one JSON metadata file under
`.continuity/` at the project root (FR-001). No database engine, embedded or
otherwise.

**Testing**: Plain Bash assertion scripts (`tests/test_*.sh`), run by
`tests/run_tests.sh`. No test framework dependency (rejected `bats-core`
deliberately — see research.md R6 — since it would be the project's first
external dependency, purely for developer-facing value).

**Target Platform**: macOS and Linux shells, wherever a Claude Code plugin
hook command executes (`#!/usr/bin/env bash` scripts invoked by the Claude
Code hook runner). Windows/WSL is not validated for the MVP (see Risks).

**Project Type**: Claude Code plugin — a single-project tree of shell scripts
and plugin manifest files; no frontend/backend split, no compiled artifact.

**Performance Goals**: The `SessionStart` hook (read + bound + format context)
must complete in low tens of milliseconds for a store at the ~100–200 line
soft target (Q2), so it is not perceptible against normal session-start time.
The triggering hook for a background write (`PostToolUse`, `SessionEnd`, the
explicit checkpoint command) must itself return in low tens of milliseconds —
it only decides whether to spawn a detached writer and then exits; all
consolidation work happens after the hook has already returned.

**Constraints** (from `.specify/memory/constitution.md` → Additional
Constraints, and the intent doc's answered open questions):
- No separate server process, no database installation, no cloud
  dependency, no Go or other standalone runtime (MVP).
- No LLM-based memory operation runs on every interaction; writes trigger on
  meaningful-change signals only (FR-008), with `SessionEnd` as one trigger
  among several, never the only one (FR-009).
- Memory writes are fire-and-forget background processes that never block the
  interactive response (FR-010); the background process must exit after one
  write and never bind a socket or listen for events (constitution note on the
  Q3 server/background-process boundary).
- Session-start context stays bounded to a ~100–200 line / ~5–10 KB soft
  target (Q2), never the full store, never a full prior conversation
  (FR-005).
- Every read/write fails open on any error (FR-012); a corrupted file is
  isolated to itself (FR-013); writes are atomic (FR-014).
- Concurrent writers use a short-lived, retry-then-fail-gracefully advisory
  lock (Q5) — implemented with `mkdir` (atomic on all POSIX filesystems,
  unlike `flock`, which is not portable across macOS/Linux without an
  external binary).
- `.continuity/` is git-tracked by default (Q1); the plugin documents and
  provides a low-friction opt-out (FR-020).
- Durable files (`state.md`, `decisions.md`, `tasks.md`, `learnings.md`) are
  retained indefinitely; session-handoff files under `.continuity/sessions/`
  and `.continuity/errors.log` follow a configurable retention period,
  default 60 days (Q6, Q8).
- Content loaded from `.continuity/` is injected as labeled, trusted-context
  (not instructions) — never auto-executed (Q4, FR-018).
- No permission beyond reading/writing `.continuity/` and reading project
  files needed to compute triggers (Q7) — no network access (FR-019).
- Schema-versioned via `.continuity/metadata.json`; a plugin reads its own
  and the previous schema version, migrates forward when safe, and fails open
  (skips, does not modify) on an unsupported newer version (Q9).
- Single project root only for the MVP — no monorepo/multi-worktree handling
  (Q10).

**Scale/Scope**: A single project's `.continuity/` store, read and written by
one or more concurrent Claude Code sessions on that same project. No
cross-project or cross-user memory layer (out of scope, per the intent doc).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|---|---|---|
| I. Feature branches from `develop`, merge by reviewed PR | Work happens on `001-continuity` (cut from `develop`); this plan does not touch branch/PR mechanics itself | PASS (procedural, enforced by the workflow, not by this design) |
| II. Plan before edit | This plan is written and must be reviewed before any implementation task in tasks.md starts | PASS once this document is reviewed |
| III. Tests not edited while fixing the code they cover | No existing tests to protect yet (greenfield); principle binds future bug-fix work, not this plan | PASS (not yet applicable) |
| IV. Production changes require explicit authorization | The plugin has no "production" runtime of its own; commits/PRs/releases still require explicit human authorization per the standing rules | PASS |
| V. No direct push to the default branch | This plan proposes no direct push to `main` or `develop` | PASS (procedural) |
| Distribution shape (marketplace-only, no Go) | Design uses only Bash + coreutils, ships as a `.claude-plugin/` manifest + marketplace listing | PASS |
| Feel unchanged / no blocking | `SessionStart` load and trigger-detection hooks are synchronous and cheap; all consolidation work is detached | PASS |
| No new infrastructure for MVP | No server, no DB, no cloud call anywhere in the design | PASS |
| Memory writes not per-interaction | Writes gate on meaningful-change signals (§Technical Context → Constraints); `SessionEnd` is one of several triggers | PASS |
| Bounded context | `SessionStart` hook enforces the ~100–200 line soft target before injecting anything | PASS |
| Fail open | Every script wraps its operation and always exits 0 from the hook's perspective, logging failures to `errors.log` | PASS |

**No violations.** The Complexity Tracking table below is intentionally empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-continuity/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
├── contracts/            # Phase 1 output
│   ├── hook-io-contract.md
│   └── file-format-contract.md
└── tasks.md              # Phase 2 output (/speckit-tasks)
```

### Source Code (repository root)

This repository *is* the plugin and its marketplace source — there is no
separate `src/`+`tests/` split by layer, because the whole feature is a small
tree of shell scripts around a fixed set of hook events.

```text
.claude-plugin/
├── marketplace.json        # GitHub marketplace listing for this repo
└── plugin.json             # Plugin manifest: name, version, hooks entrypoint

hooks/
├── hooks.json               # Registers SessionStart, PostToolUse, SessionEnd
├── session-start.sh          # Loads + bounds + labels context, emits it
├── capture-trigger.sh         # PostToolUse: detects a meaningful-change
│                               # signal, spawns a detached writer if so
└── session-end.sh              # SessionEnd: spawns a detached final-checkpoint
                                  # writer

commands/
└── continuity-checkpoint.md    # /continuity-checkpoint: explicit checkpoint
                                  # trigger (FR-008); Claude writes the staged
                                  # note first (see Content Channel below),
                                  # then invokes lib/write_memory.sh

lib/
├── common.sh                   # Shared paths, logging, config resolution
├── lock.sh                     # mkdir-based advisory lock: acquire/release/
│                                 # stale-break
├── atomic_write.sh              # write-to-temp-then-rename helper
├── secret_scan.sh                # Lightweight regex secret-pattern gate
├── select_context.sh              # SessionStart bounding/selection logic
├── write_memory.sh                 # Background writer: consolidates a
│                                     # pre-written staged note (see Content
│                                     # Channel below) into the durable files
├── migrate.sh                       # Reads/writes metadata.json, migrates
│                                      # schema versions forward when safe
└── retention.sh                      # Prunes sessions/ and errors.log by
                                        # configured retention window

templates/
├── state.md.tmpl
├── decisions.md.tmpl
├── tasks.md.tmpl
├── learnings.md.tmpl
└── metadata.json.tmpl

docs/
├── intent/continuity.md        # (existing)
└── install.md                  # Install steps + the .gitignore opt-out
                                  # documented by FR-020

tests/
├── run_tests.sh
├── test_lock.sh
├── test_atomic_write.sh
├── test_secret_scan.sh
├── test_select_context.sh
├── test_fail_open.sh
├── test_migrate.sh
└── test_retention.sh
```

Runtime data created *in an installed project* (not shipped by this repo,
produced the first time a trigger or `SessionStart` runs there):

```text
.continuity/
├── metadata.json        # schema_version, plugin_version, retention config
├── state.md              # current state + a "## Constraints" section
├── decisions.md            # Decision Records
├── tasks.md                 # Task Entries
├── learnings.md               # Learnings + a "## Conventions" section
├── errors.log                  # Failure Log Entries (scrubbed, retained per
│                                 config, default 60 days)
├── sessions/                     # Session Handoffs, one file per checkpoint,
│   └── <UTC-timestamp>-<pid>.md   # pruned per config, default 60 days
├── .staged/                        # Claude-written notes awaiting
│   └── <kind>-<timestamp>-<pid>.md  # consolidation; consumed and removed by
│                                     # write_memory.sh (see Content Channel)
└── .lock/                          # transient; created by lib/lock.sh,
                                      # removed on release or stale-break
```

## Content Channel (resolves analyze finding C1)

`write_memory.sh` is pure shell — it consolidates, it never composes prose,
per the "no LLM-based memory operation" constraint above. But a Decision's
rationale, a Learning's body, a Task's description, and a Handoff's summary
are natural-language content only Claude (the agent in the session, not the
hook) can produce. No hook receives that text today: `capture-trigger.sh`
and `session-end.sh` fire from tool-call/session-end payloads that carry no
note body, and `/continuity-checkpoint` invokes `write_memory.sh` with no
content argument either. This is the gap analyze's C1 finding names.

**Fix**: Claude stages the note itself, as a file, before any trigger runs
`write_memory.sh`:

1. When Claude recognizes it has just made a decision, finished a task,
   learned something worth keeping, or is closing a session, it writes one
   small staged-note file via its own Write tool to
   `.continuity/.staged/<kind>-<UTC-timestamp>-<pid>.md` — `<kind>` is one of
   `decision`, `task`, `learning`, `handoff`. The note body is exactly the
   prose Claude already composed; no new format to learn, just a file
   instead of a chat message.
2. Only after the staged file exists does the relevant trigger run:
   `/continuity-checkpoint` (T018) checks `.continuity/.staged/` itself
   before invoking `write_memory.sh`; `capture-trigger.sh` and
   `session-end.sh` are unchanged — they still detach `write_memory.sh`
   unconditionally on their existing signals, and a run with nothing staged
   is FR-011's ordinary no-op.
3. `write_memory.sh <cwd> <trigger-kind>` reads every file currently in
   `.continuity/.staged/`, secret-scans and appends each one into the
   matching durable file (`decisions.md`/`tasks.md`/`learnings.md`/the
   `sessions/*.md` handoff) via `atomic_write.sh`, then removes the staged
   file it consumed — consolidation only, exactly as already planned. A
   staged file with no corresponding trigger simply waits for the next one
   (`capture-trigger.sh` or `SessionEnd`) rather than being lost.
4. Fail-open applies here too (FR-012): if a staged file is malformed or the
   secret scanner rejects a line, that line (or the whole staged file, if
   nothing survives) is dropped and logged to `errors.log`, and
   `write_memory.sh` still exits 0 having consolidated whatever else it
   found.

This keeps every existing constraint intact — no LLM call inside the hook
path, no new content on every interaction, background writes stay
fire-and-forget — because the composition step is something Claude was
already going to do (recognize and phrase the note); staging it as a file is
the only new mechanism, and it is a plain filesystem write, not a process or
a socket.

See `contracts/hook-io-contract.md`'s new "Content Channel" section for the
staged-note file format, and `tasks.md` T017a for the task this adds.

**Structure Decision**: Single-project, shell-only layout. `hooks/` and
`commands/` are the plugin's event surface; `lib/` holds every piece of
reusable logic so each hook script stays a thin dispatcher (easier to keep
each hook fast and testable in isolation); `templates/` seeds a brand-new
`.continuity/` store; `tests/` mirrors `lib/` one-to-one. This groups files by
what they *are* (hook, library function, template, test) rather than by user
story, because every user story in the spec is a cross-cutting property of
the same small set of files (there is no per-story vertical slice to isolate).

## Complexity Tracking

*No violations — table intentionally empty.*

## Files That Change

Every file this feature introduces, grouped by the order they are built in
(§Implementation Order below assigns each group a phase):

| File | Purpose |
|---|---|
| `.claude-plugin/plugin.json` | Plugin manifest (name, version, hook entrypoint) |
| `.claude-plugin/marketplace.json` | Marketplace listing so the plugin is installable from this repo |
| `lib/common.sh` | Path resolution (`.continuity/` location, config load), shared logging |
| `lib/atomic_write.sh` | Write-to-temp-then-rename primitive used by every writer |
| `lib/lock.sh` | `mkdir`-based advisory lock: acquire (with timeout+retry), release, stale-break |
| `lib/secret_scan.sh` | Regex gate run on any line before it is persisted |
| `lib/migrate.sh` | Reads/creates `metadata.json`; schema-version compatibility check and forward migration |
| `templates/*.tmpl` | Seed content for a first-ever `.continuity/` store |
| `lib/select_context.sh` | Reads the durable files + recent session handoffs, bounds to the ~100–200 line target, labels provenance |
| `hooks/session-start.sh` | Calls `select_context.sh`, emits the `additionalContext` hook output, fails open |
| `lib/write_memory.sh` | Consolidates every staged note in `.continuity/.staged/` into `state.md`/`decisions.md`/`tasks.md`/`learnings.md`/`sessions/*.md`, using `lock.sh` + `atomic_write.sh` + `secret_scan.sh`, then removes each consumed staged file |
| `hooks/capture-trigger.sh` | `PostToolUse` dispatcher: classifies whether the just-completed tool call is a meaningful-change signal; if so, detaches `write_memory.sh` and returns immediately |
| `hooks/session-end.sh` | `SessionEnd` dispatcher: always detaches a final-checkpoint `write_memory.sh` call |
| `commands/continuity-checkpoint.md` | Explicit `/continuity-checkpoint` slash command wired to `write_memory.sh` |
| `hooks/hooks.json` | Registers the three hooks above against their events/matchers |
| `lib/retention.sh` | Prunes `.continuity/sessions/*` and trims `errors.log` per the configured retention window |
| `docs/install.md` | Documents the git-tracked default and the `.gitignore` opt-out (FR-020) |
| `tests/*.sh` | One test file per `lib/*.sh` module, plus `run_tests.sh` |

No existing file in this repository is modified by this feature; everything
above is new. (`docs/intent/continuity.md`, `specs/001-continuity/spec.md`,
and `.specify/memory/constitution.md` are inputs, read-only.)

## Implementation Order

Ordered so that every phase after Phase 1 has something real underneath it to
test against — no phase depends on a file that a later phase creates.

1. **Foundation primitives (no hook wiring yet)**: `lib/common.sh`,
   `lib/atomic_write.sh`, `lib/lock.sh`, `lib/secret_scan.sh`,
   `lib/migrate.sh`, `templates/*.tmpl`. Each is independently testable
   against a scratch directory — this is where most of the correctness risk
   lives (see Risks), so it goes first and gets the most test coverage.
2. **Read path**: `lib/select_context.sh`, then `hooks/session-start.sh` as a
   thin wrapper around it. Built second because it has no write-side
   concurrency concerns and directly proves FR-005/FR-006/FR-007.
3. **Write path**: `lib/write_memory.sh` (uses every Phase 1 primitive), then
   `hooks/capture-trigger.sh` and `hooks/session-end.sh` as thin dispatchers
   around it, then `commands/continuity-checkpoint.md`. Built third because it
   is the highest-risk phase (detachment + locking + secret-scanning all
   compose here) and benefits from Phase 1's primitives already being proven.
4. **Retention**: `lib/retention.sh`, invoked from the end of
   `write_memory.sh`'s successful run (so pruning piggybacks on an already-
   scheduled background process rather than adding a new trigger).
5. **Plugin packaging**: `.claude-plugin/plugin.json`,
   `.claude-plugin/marketplace.json`, `hooks/hooks.json` wiring the Phase 2–3
   scripts to real events. Deliberately last among the code changes — wiring
   real Claude Code hook events is the one part of this plan that cannot be
   fully exercised by the plain-Bash test suite (see Risks), so it is built
   once the logic underneath it is already trustworthy.
6. **Docs**: `docs/install.md`. Last, since it documents the shipped
   behavior rather than shaping it.

Corresponds to `tasks.md` Phase 1 (Setup) through Phase 3+ (user stories) —
see that file for task-level granularity, dependencies, and `Done when`
conditions.

## Testing Strategy

- **Unit-level, per `lib/*.sh` module** (`tests/test_*.sh`, run via
  `tests/run_tests.sh`, plain Bash assertions, no framework):
  - `test_lock.sh`: two subshells racing `lock.sh acquire` on the same path —
    exactly one succeeds immediately, the other retries and either succeeds
    after release or fails gracefully after timeout; a lock directory older
    than the stale threshold is broken and re-acquired.
  - `test_atomic_write.sh`: a write that is killed mid-way (simulated by
    writing to the temp path and never renaming) leaves the original file, if
    any, completely intact and unreadable-partial-state-free.
  - `test_secret_scan.sh`: known secret-shaped strings (AWS-style key,
    generic `api_key=`, a PEM private-key header) are rejected; ordinary
    project prose is accepted unchanged.
  - `test_select_context.sh`: a store built to exceed the ~100–200 line
    target is bounded on output; a store with zero prior history returns
    empty with no error (proves FR-005/FR-007).
  - `test_migrate.sh`: a file at the current schema version is read
    unchanged; a file at the previous version is migrated forward; a file at
    an unsupported newer version is left untouched and the read fails open.
  - `test_retention.sh`: a session file older than the retention window is
    pruned; one inside the window is kept; durable files are never pruned
    regardless of age.
  - `test_fail_open.sh`: a missing `.continuity/` directory, an unreadable
    file (permission-denied), and a corrupted (truncated/invalid) file each
    cause the affected operation to be skipped and logged, with every *other*
    valid file still loading (proves FR-012/FR-013).
- **Integration-level** (also plain Bash, driving the hook scripts directly
  by feeding them the JSON stdin payload Claude Code would send, per
  `contracts/hook-io-contract.md`):
  - `hooks/session-start.sh` against a fixture `.continuity/` store, asserting
    the emitted `additionalContext` is labeled as Continuity context (Q4),
    bounded, and provenance-tagged (FR-004).
  - `hooks/capture-trigger.sh` fed a non-meaningful signal (whitespace-only
    diff) asserts *no* file is written and *no* failure is logged (spec's
    documented no-op edge case).
  - `hooks/session-end.sh` and `commands/continuity-checkpoint.md`'s target
    script asserting a checkpoint file appears under `.continuity/sessions/`.
- **Manual/quickstart-level** (`quickstart.md`): the two-session narrative
  from the spec's own Independent Test for User Story 1 — work a session to a
  decision + an unfinished task, end it, start a new session, confirm the
  injected context contains both, run once with Continuity installed and once
  without to eyeball User Story 2's "no perceptible difference," and
  deliberately corrupt/delete `.continuity/` to exercise User Story 3.
- **What is deliberately not automated**: true concurrent-process races
  against the real filesystem (`test_lock.sh` simulates concurrency with
  subshells, which does not fully replicate two independent OS processes),
  and the real Claude Code hook runtime itself (the test suite calls the hook
  scripts directly with a crafted stdin payload; it does not install the
  plugin into a live Claude Code session). Both are called out in Risks
  below as gaps a human must additionally verify before release.

## Risks & Self-Review

**What could this break?** Nothing in an existing codebase — this is a
greenfield plugin with no existing consumers. The risk surface is entirely
about whether the feature does what the spec promises once installed
somewhere real:
- A bug in `capture-trigger.sh`'s meaningful-change classification could
  either (a) never fire, silently defeating User Story 1, or (b) fire on
  every tool call, silently violating FR-008/User Story 2's "no LLM operation
  and no perceptible cost per interaction" bar. Both failure modes are
  invisible from normal use — that is why `test_select_context.sh` and the
  quickstart's timed comparison both exist.
- A bug in `atomic_write.sh` or `lock.sh` could corrupt a durable file for
  every future session on that project, not just the session that triggered
  the bad write — this is the one place where a bug's blast radius extends
  past a single session. It is why Phase 1 (Foundation primitives) is
  ordered first and tested most heavily.
- A secret-scan false negative in `secret_scan.sh` ships a credential into
  git-tracked history exactly as the spec's Concerns section warned about;
  a false positive silently drops a legitimate decision. Neither is fully
  preventable by a regex gate — `docs/install.md` must say plainly that the
  scan is a mitigation, not a guarantee, so a developer does not treat it as
  a substitute for their own judgment about what they let Continuity write.

**Which step is riskiest?** Phase 3 (the write path: `write_memory.sh` +
its two hook dispatchers + the explicit checkpoint command). It is the only
place where detachment, locking, atomic writes, and secret-scanning all
compose in one code path, and it is the one path this plan cannot fully test
without a real Claude Code runtime (see Testing Strategy → "what is
deliberately not automated"). Concretely: if `capture-trigger.sh` does not
correctly detach its background writer (e.g., the writer is still a child of
the hook process rather than reparented), the hook runner could wait on it
before returning, silently reintroducing the exact per-interaction latency
User Story 2 exists to prevent — and this would only surface as "Continuity
feels slow sometimes," not as a test failure. Mitigation: `test_fail_open.sh`
and a dedicated manual timing check in `quickstart.md` are the two closest
proxies available pre-release; a real-runtime timing measurement is called
out as a required post-implementation follow-up (the spec's own SC-006
already defers a quantitative latency threshold to post-MVP measurement).

**What was rejected, and why?**
- *Python for the writer/selector logic* — rejected because it adds a
  runtime dependency (however commonly preinstalled) the constitution does
  not clearly permit for the MVP ("no Go or other standalone runtime"), when
  Bash and coreutils are guaranteed present everywhere Claude Code's own
  hook mechanism already runs shell commands. See research.md R1.
- *`flock` for locking* — rejected because it is not part of base macOS
  (BSD userland ships no `flock` binary by default), so it would need to be
  installed or a Linux-only code path maintained; `mkdir`'s atomicity is a
  POSIX guarantee on every target platform with no such gap. See
  research.md R2.
- *An embedded key-value store (e.g., a single SQLite file) for the
  session-start index* — rejected even though SQLite is not a "database
  installation" in the traditional sense, because Q2's answer explicitly
  scopes the MVP to file-based selection without an embedded store, and
  because it would reintroduce exactly the "what counts as a database"
  ambiguity Q2 was written to close. Revisit only if pure file-based bounding
  is measured to be insufficient post-MVP, per Q2/Q6's own deferred
  follow-up. See research.md R3.
- *A single undifferentiated `.continuity/log.md`* instead of four purpose-
  named durable files — rejected because Q6 explicitly answers with four
  named files (`state.md`, `decisions.md`, `tasks.md`, `learnings.md`), and a
  single log would make FR-004's provenance requirement (category +
  timestamp per entry) harder to satisfy cleanly and would make bounding
  (FR-005) require parsing rather than a per-file line budget.
- *`bats-core` (or another shell test framework)* for the test suite —
  rejected per SC-005's "exactly one new dependency: the plugin itself";
  even as a dev-only dependency it is unnecessary weight when plain Bash
  assertions fully cover this feature's logic. See research.md R6.
- *A dedicated `constraints.md` file* for the Constraint entity — rejected
  because Q6 names exactly four durable files and does not include one for
  constraints; constraints are folded into `state.md` under a `##
  Constraints` heading instead (see data-model.md).
