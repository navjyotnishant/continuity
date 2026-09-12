# Implementation Plan: Continuity

**Branch**: `001-continuity` | **Date**: 2026-09-12 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-continuity/spec.md`, grounded in
`docs/intent/continuity.md` and `.specify/memory/constitution.md`.

## Summary

Continuity is a Claude Code plugin, distributed via a GitHub-hosted marketplace,
that gives a Claude Code session memory of a project's prior sessions without a
server, a database, or a cloud dependency. It persists project-scoped context —
state, decisions, tasks, learnings, and session handoffs — as plain
Markdown/text files under `.continuity/` at the project root. A `SessionStart`
hook loads a bounded (~100–200 line soft target), provenance-labeled subset of
that store as injected context. Writes are triggered by meaningful-change
signals (file changes, git diffs, task/decision events, explicit checkpoints,
`SessionEnd`) rather than every interaction, and execute as a detached,
fire-and-forget background process so the triggering hook returns immediately.
Every read and write fails open: on any error the operation is skipped, logged
locally, and Claude Code continues unaffected.

The implementation is Python, standard library only — no third-party packages,
no `pip install` step, no `requirements.txt`/`pyproject.toml` dependency list.
Python is not a new runtime this plugin introduces: it is already required to
run Claude Code hooks in this environment, so choosing it satisfies the
constitution's "no Go or any other standalone runtime for the MVP" constraint
the same way Bash would have, without actually needing Bash's POSIX-portability
workarounds (see the September 12 correction in Risks → "What was rejected, and
why" — this repersects an earlier revision of this plan that chose Bash; the
user has since confirmed Python is the required language for this project).

## Technical Context

**Language/Version**: Python 3.9+, standard library only (Q11). No Bash,
Node, or Go. Every stdlib API this plan relies on must exist on 3.9 across
macOS, Linux, and native Windows.

**Primary Dependencies**: None. Every operation uses only Python's standard
library (`os`, `sys`, `json`, `re`, `shutil`, `tempfile`, `subprocess`,
`datetime`, `argparse`, `pathlib`, `unittest`) — modules that ship with any
Python 3 interpreter. No package manager, no `pip install` step, no vendored
library, no `requirements.txt`.

**Storage**: Plain Markdown/text files plus one JSON metadata file under
`.continuity/` at the project root (FR-001). No database engine, embedded or
otherwise. Unaffected by the language choice.

**Testing**: Python's standard-library `unittest` (`tests/test_*.py`), run by
`python3 -m unittest discover -s tests` (wrapped by `tests/run_tests.py` for a
single entry point). No third-party test framework — `pytest` was considered
and rejected for the same reason the earlier Bash-based plan rejected
`bats-core`: it would be the project's first external dependency, purely for
developer-facing convenience, when stdlib `unittest` fully covers this
feature's logic. See research.md R6.

**Target Platform**: macOS, Linux, and native Windows (not WSL-only) — Q11.
Every hook is invoked explicitly (`python3 hooks/session-start.py` /
`python.exe hooks\session-start.py` per `hooks.json`, never a
`#!/usr/bin/env python3` shebang), so the interpreter is named the way each
platform's Claude Code hook runner expects. Native-Windows support means the
detachment and atomic-write mechanisms (§Constraints below) need a real
Windows code path, not a POSIX-only implementation with Windows punted to
Risks.

**Project Type**: Claude Code plugin — a single-project tree of Python scripts
and plugin manifest files; no frontend/backend split, no compiled artifact, no
build step (Python is interpreted directly).

**Performance Goals**: The `SessionStart` hook (read + bound + format context)
must complete in low tens of milliseconds for a store at the ~100–200 line
soft target (Q2), so it is not perceptible against normal session-start time.
The triggering hook for a background write (`PostToolUse`, `SessionEnd`, the
explicit checkpoint command) must itself return in low tens of milliseconds —
it only decides whether to spawn a detached writer and then exits; all
consolidation work happens after the hook has already returned. A Python
interpreter's cold-start cost is higher than a shell script's near-zero fork
cost, which this design did not previously have to budget for — see Risks
below for why this needs to be measured, not assumed.

**Constraints** (from `.specify/memory/constitution.md` → Additional
Constraints, and the intent doc's answered open questions):
- No separate server process, no database installation, no cloud
  dependency, no Go or other standalone runtime beyond the Python interpreter
  Claude Code hooks already require (MVP).
- No LLM-based memory operation runs on every interaction; writes trigger on
  meaningful-change signals only (FR-008), with `SessionEnd` as one trigger
  among several, never the only one (FR-009).
- Memory writes are fire-and-forget background processes that never block the
  interactive response (FR-010); the background process must exit after one
  write and never bind a socket or listen for events (constitution note on the
  Q3 server/background-process boundary). Implemented with
  `subprocess.Popen(..., stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL,
  close_fds=True, **detach_kwargs)`, where `detach_kwargs` branches on
  `os.name`: `{"start_new_session": True}` on POSIX (`posix`) so the writer is
  reparented away from the hook process rather than left as its child (see
  Risks → riskiest step), and `{"creationflags":
  subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}` on
  native Windows (`nt`) — `DETACHED_PROCESS` gives the writer no console to
  inherit and `CREATE_NEW_PROCESS_GROUP` keeps it out of the hook process's
  process group, the Windows equivalent of session detachment. Both branches
  ship in the MVP; neither platform's path is deferred to Risks.
- Session-start context stays bounded to a ~100–200 line / ~5–10 KB soft
  target (Q2), never the full store, never a full prior conversation
  (FR-005).
- Every read/write fails open on any error (FR-012); a corrupted file is
  isolated to itself (FR-013); writes are atomic (FR-014), implemented with
  `tempfile.NamedTemporaryFile` (same directory as the target, so the
  replace stays on one filesystem) followed by `os.replace()` — atomic on
  both POSIX and Windows, the same guarantee the Bash design got from
  write-to-temp-then-`mv`.
- Concurrent writers use a short-lived, retry-then-fail-gracefully advisory
  lock (Q5) — implemented with `os.mkdir()` (atomic directory creation raises
  `FileExistsError` if the directory already exists, the same atomicity
  guarantee the earlier Bash design relied on `mkdir` for, and it is portable
  across macOS, Linux, and native Windows with no external binary needed,
  unlike `flock` (POSIX-only) or a named-mutex API (Windows-only)).
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
| Distribution shape (marketplace-only, no Go) | Design uses only Python's standard library, ships as a `.claude-plugin/` manifest + marketplace listing | PASS |
| Feel unchanged / no blocking | `SessionStart` load and trigger-detection hooks are synchronous and cheap; all consolidation work is detached | PASS, pending the interpreter-startup measurement flagged in Risks |
| No new infrastructure for MVP | No server, no DB, no cloud call anywhere in the design; Python is the interpreter Claude Code hooks already require, not a newly-introduced standalone runtime | PASS |
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
tree of Python scripts around a fixed set of hook events.

```text
.claude-plugin/
├── marketplace.json        # GitHub marketplace listing for this repo
└── plugin.json             # Plugin manifest: name, version, hooks entrypoint

hooks/
├── hooks.json               # Registers SessionStart, PostToolUse, SessionEnd;
│                               each entry invokes `python3 hooks/<script>.py`
│                               explicitly (no shebang dependency)
├── session-start.py          # Loads + bounds + labels context, emits it
├── capture-trigger.py         # PostToolUse: detects a meaningful-change
│                               # signal, spawns a detached writer if so
└── session-end.py              # SessionEnd: spawns a detached final-checkpoint
                                  # writer

commands/
└── continuity-checkpoint.md    # /continuity-checkpoint: explicit checkpoint
                                  # trigger (FR-008); Claude writes the staged
                                  # note first (see Content Channel below),
                                  # then invokes lib/write_memory.py

lib/
├── common.py                   # Shared paths, logging, config resolution
├── lock.py                     # os.mkdir()-based advisory lock: acquire/
│                                 # release/stale-break
├── atomic_write.py              # write-to-temp-then-os.replace() helper
├── secret_scan.py                # Lightweight regex secret-pattern gate
├── select_context.py              # SessionStart bounding/selection logic
├── write_memory.py                 # Background writer: consolidates a
│                                     # pre-written staged note (see Content
│                                     # Channel below) into the durable files
├── migrate.py                       # Reads/writes metadata.json, migrates
│                                      # schema versions forward when safe
└── retention.py                      # Prunes sessions/ and errors.log by
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
├── run_tests.py
├── test_lock.py
├── test_atomic_write.py
├── test_secret_scan.py
├── test_select_context.py
├── test_fail_open.py
├── test_migrate.py
└── test_retention.py
```

`lib/*.py` modules use underscore filenames (not hyphens) so they can `import`
one another as ordinary Python modules; `hooks/*.py` scripts are invoked
directly by `hooks.json` and never imported, so they keep the existing
hyphenated naming for consistency with `commands/continuity-checkpoint.md` and
the rest of the plugin's file naming.

Runtime data created *in an installed project* (not shipped by this repo,
produced the first time a trigger or `SessionStart` runs there) is unchanged
by the language choice — file formats stay Markdown/JSON either way:

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
│                                     # write_memory.py (see Content Channel)
└── .lock/                          # transient; created by lib/lock.py,
                                      # removed on release or stale-break
```

## Content Channel (resolves analyze finding C1)

`write_memory.py` is a plain script — it consolidates, it never composes
prose, per the "no LLM-based memory operation" constraint above. But a
Decision's rationale, a Learning's body, a Task's description, and a
Handoff's summary are natural-language content only Claude (the agent in the
session, not the hook) can produce. No hook receives that text today:
`capture-trigger.py` and `session-end.py` fire from tool-call/session-end
payloads that carry no note body, and `/continuity-checkpoint` invokes
`write_memory.py` with no content argument either. This is the gap analyze's
C1 finding names.

**Fix**: Claude stages the note itself, as a file, before any trigger runs
`write_memory.py`:

1. When Claude recognizes it has just made a decision, finished a task,
   learned something worth keeping, or is closing a session, it writes one
   small staged-note file via its own Write tool to
   `.continuity/.staged/<kind>-<UTC-timestamp>-<pid>.md` — `<kind>` is one of
   `decision`, `task`, `learning`, `handoff`. The note body is exactly the
   prose Claude already composed; no new format to learn, just a file
   instead of a chat message.
2. Only after the staged file exists does the relevant trigger run:
   `/continuity-checkpoint` (T018) checks `.continuity/.staged/` itself
   before invoking `write_memory.py`; `capture-trigger.py` and
   `session-end.py` are unchanged — they still detach `write_memory.py`
   unconditionally on their existing signals, and a run with nothing staged
   is FR-011's ordinary no-op.
3. `write_memory.py <cwd> <trigger-kind>` reads every file currently in
   `.continuity/.staged/`, secret-scans and appends each one into the
   matching durable file (`decisions.md`/`tasks.md`/`learnings.md`/the
   `sessions/*.md` handoff) via `atomic_write.py`, then removes the staged
   file it consumed — consolidation only, exactly as already planned. A
   staged file with no corresponding trigger simply waits for the next one
   (`capture-trigger.py` or `SessionEnd`) rather than being lost.
4. Fail-open applies here too (FR-012): if a staged file is malformed or the
   secret scanner rejects a line, that line (or the whole staged file, if
   nothing survives) is dropped and logged to `errors.log`, and
   `write_memory.py` still exits 0 having consolidated whatever else it
   found.

This keeps every existing constraint intact — no LLM call inside the hook
path, no new content on every interaction, background writes stay
fire-and-forget — because the composition step is something Claude was
already going to do (recognize and phrase the note); staging it as a file is
the only new mechanism, and it is a plain filesystem write, not a process or
a socket.

See `contracts/hook-io-contract.md`'s new "Content Channel" section for the
staged-note file format, and `tasks.md` T017a for the task this adds.

**Structure Decision**: Single-project, script-only layout. `hooks/` and
`commands/` are the plugin's event surface; `lib/` holds every piece of
reusable logic so each hook script stays a thin dispatcher (easier to keep
each hook fast and testable in isolation); `templates/` seeds a brand-new
`.continuity/` store; `tests/` mirrors `lib/` one-to-one. This groups files by
what they *are* (hook, library module, template, test) rather than by user
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
| `lib/common.py` | Path resolution (`.continuity/` location, config load), shared logging |
| `lib/atomic_write.py` | Write-to-temp-then-`os.replace()` primitive used by every writer |
| `lib/lock.py` | `os.mkdir()`-based advisory lock: acquire (with timeout+retry), release, stale-break |
| `lib/secret_scan.py` | Regex gate (via `re`) run on any line before it is persisted |
| `lib/migrate.py` | Reads/creates `metadata.json`; schema-version compatibility check and forward migration |
| `templates/*.tmpl` | Seed content for a first-ever `.continuity/` store |
| `lib/select_context.py` | Reads the durable files + recent session handoffs, bounds to the ~100–200 line target, labels provenance |
| `hooks/session-start.py` | Calls `select_context.py`, emits the `additionalContext` hook output, fails open |
| `lib/write_memory.py` | Consolidates every staged note in `.continuity/.staged/` into `state.md`/`decisions.md`/`tasks.md`/`learnings.md`/`sessions/*.md`, using `lock.py` + `atomic_write.py` + `secret_scan.py`, then removes each consumed staged file |
| `hooks/capture-trigger.py` | `PostToolUse` dispatcher: classifies whether the just-completed tool call is a meaningful-change signal; if so, detaches `write_memory.py` (via `subprocess.Popen` with the POSIX/Windows `detach_kwargs` branch from §Constraints) and returns immediately |
| `hooks/session-end.py` | `SessionEnd` dispatcher: always detaches a final-checkpoint `write_memory.py` call |
| `commands/continuity-checkpoint.md` | Explicit `/continuity-checkpoint` slash command wired to `write_memory.py` |
| `hooks/hooks.json` | Registers the three hooks above against their events/matchers, each command invoking `python3 hooks/<script>.py` explicitly |
| `lib/retention.py` | Prunes `.continuity/sessions/*` and trims `errors.log` per the configured retention window |
| `docs/install.md` | Documents the git-tracked default and the `.gitignore` opt-out (FR-020), and states the minimum Python version (3.9+, macOS/Linux/native Windows — Q11) |
| `tests/*.py` | One `unittest`-based test file per `lib/*.py` module, plus `run_tests.py` |

No existing file in this repository is modified by this feature; everything
above is new. (`docs/intent/continuity.md`, `specs/001-continuity/spec.md`,
and `.specify/memory/constitution.md` are inputs, read-only.)

## Implementation Order

Ordered so that every phase after Phase 1 has something real underneath it to
test against — no phase depends on a file that a later phase creates.

1. **Foundation primitives (no hook wiring yet)**: `lib/common.py`,
   `lib/atomic_write.py`, `lib/lock.py`, `lib/secret_scan.py`,
   `lib/migrate.py`, `templates/*.tmpl`. Each is independently testable
   against a scratch directory — this is where most of the correctness risk
   lives (see Risks), so it goes first and gets the most test coverage.
2. **Read path**: `lib/select_context.py`, then `hooks/session-start.py` as a
   thin wrapper around it. Built second because it has no write-side
   concurrency concerns and directly proves FR-005/FR-006/FR-007.
3. **Write path**: `lib/write_memory.py` (uses every Phase 1 primitive), then
   `hooks/capture-trigger.py` and `hooks/session-end.py` as thin dispatchers
   around it, then `commands/continuity-checkpoint.md`. Built third because it
   is the highest-risk phase (detachment + locking + secret-scanning all
   compose here) and benefits from Phase 1's primitives already being proven.
4. **Retention**: `lib/retention.py`, invoked from the end of
   `write_memory.py`'s successful run (so pruning piggybacks on an already-
   scheduled background process rather than adding a new trigger).
5. **Plugin packaging**: `.claude-plugin/plugin.json`,
   `.claude-plugin/marketplace.json`, `hooks/hooks.json` wiring the Phase 2–3
   scripts to real events. Deliberately last among the code changes — wiring
   real Claude Code hook events is the one part of this plan that cannot be
   fully exercised by the `unittest` suite (see Risks), so it is built once
   the logic underneath it is already trustworthy.
6. **Docs**: `docs/install.md`. Last, since it documents the shipped
   behavior rather than shaping it.

Corresponds to `tasks.md` Phase 1 (Setup) through Phase 3+ (user stories) —
see that file for task-level granularity, dependencies, and `Done when`
conditions.

## Testing Strategy

- **Unit-level, per `lib/*.py` module** (`tests/test_*.py`, run via
  `python3 -m unittest discover -s tests` / `tests/run_tests.py`, stdlib
  `unittest`, no third-party framework):
  - `test_lock.py`: two independent OS processes (spawned with
    `multiprocessing.Process` or `subprocess.Popen`, not merely subshells —
    an improvement over the earlier Bash design's simulated concurrency,
    since Python's stdlib makes launching genuinely separate processes as
    easy as launching threads) racing `lock.acquire()` on the same path —
    exactly one succeeds immediately, the other retries and either succeeds
    after release or fails gracefully after timeout; a lock directory older
    than the stale threshold is broken and re-acquired.
  - `test_atomic_write.py`: a write that is killed mid-way (simulated by
    writing to the temp path and never calling `os.replace()`) leaves the
    original file, if any, completely intact and unreadable-partial-state-
    free.
  - `test_secret_scan.py`: known secret-shaped strings (AWS-style key,
    generic `api_key=`, a PEM private-key header) are rejected; ordinary
    project prose is accepted unchanged.
  - `test_select_context.py`: a store built to exceed the ~100–200 line
    target is bounded on output; a store with zero prior history returns
    empty with no error (proves FR-005/FR-007).
  - `test_migrate.py`: a file at the current schema version is read
    unchanged; a file at the previous version is migrated forward; a file at
    an unsupported newer version is left untouched and the read fails open.
  - `test_retention.py`: a session file older than the retention window is
    pruned; one inside the window is kept; durable files are never pruned
    regardless of age.
  - `test_fail_open.py`: a missing `.continuity/` directory, an unreadable
    file (permission-denied), and a corrupted (truncated/invalid) file each
    cause the affected operation to be skipped and logged, with every *other*
    valid file still loading (proves FR-012/FR-013).
- **Integration-level** (also `unittest`, driving the hook scripts directly
  by feeding them the JSON stdin payload Claude Code would send, per
  `contracts/hook-io-contract.md`):
  - `hooks/session-start.py` against a fixture `.continuity/` store, asserting
    the emitted `additionalContext` is labeled as Continuity context (Q4),
    bounded, and provenance-tagged (FR-004).
  - `hooks/capture-trigger.py` fed a non-meaningful signal (whitespace-only
    diff) asserts *no* file is written and *no* failure is logged (spec's
    documented no-op edge case).
  - `hooks/session-end.py` and `commands/continuity-checkpoint.md`'s target
    script asserting a checkpoint file appears under `.continuity/sessions/`.
- **Manual/quickstart-level** (`quickstart.md`): the two-session narrative
  from the spec's own Independent Test for User Story 1 — work a session to a
  decision + an unfinished task, end it, start a new session, confirm the
  injected context contains both, run once with Continuity installed and once
  without to eyeball User Story 2's "no perceptible difference," and
  deliberately corrupt/delete `.continuity/` to exercise User Story 3.
- **What is deliberately not automated**: the real Claude Code hook runtime
  itself (the test suite calls the hook scripts directly with a crafted
  stdin payload; it does not install the plugin into a live Claude Code
  session). Called out in Risks below as a gap a human must additionally
  verify before release. (True concurrent-process locking, unlike in the
  Bash design, *is* now automatable via `multiprocessing`/`subprocess` — see
  `test_lock.py` above.)

## Risks & Self-Review

**What could this break?** Nothing in an existing codebase — this is a
greenfield plugin with no existing consumers. The risk surface is entirely
about whether the feature does what the spec promises once installed
somewhere real:
- A bug in `capture-trigger.py`'s meaningful-change classification could
  either (a) never fire, silently defeating User Story 1, or (b) fire on
  every tool call, silently violating FR-008/User Story 2's "no LLM operation
  and no perceptible cost per interaction" bar. Both failure modes are
  invisible from normal use — that is why `test_select_context.py` and the
  quickstart's timed comparison both exist.
- A bug in `atomic_write.py` or `lock.py` could corrupt a durable file for
  every future session on that project, not just the session that triggered
  the bad write — this is the one place where a bug's blast radius extends
  past a single session. It is why Phase 1 (Foundation primitives) is
  ordered first and tested most heavily.
- A secret-scan false negative in `secret_scan.py` ships a credential into
  git-tracked history exactly as the spec's Concerns section warned about;
  a false positive silently drops a legitimate decision. Neither is fully
  preventable by a regex gate — `docs/install.md` must say plainly that the
  scan is a mitigation, not a guarantee, so a developer does not treat it as
  a substitute for their own judgment about what they let Continuity write.
- **New with the Python rewrite**: a Python interpreter's cold-start latency
  is measurably higher than a shell script's near-zero fork cost. Every hook
  invocation now pays that cost on top of the actual work. If it turns out to
  exceed the low-tens-of-milliseconds budget on a representative developer
  machine, User Story 2's "feels exactly as fast" bar is at risk in a way the
  Bash design never had to guard against. This must be measured against a
  real `python3` invocation, not assumed — flagged here rather than resolved,
  since no measurement exists yet.

**Which step is riskiest?** Phase 3 (the write path: `write_memory.py` +
its two hook dispatchers + the explicit checkpoint command). It is the only
place where detachment, locking, atomic writes, and secret-scanning all
compose in one code path, and it is the one path this plan cannot fully test
without a real Claude Code runtime (see Testing Strategy → "what is
deliberately not automated"). Concretely: if `capture-trigger.py` does not
correctly detach its background writer (e.g., `subprocess.Popen` is called
without `start_new_session=True` on POSIX, or without
`CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS` on Windows, leaving the writer a
child of the hook process), the hook runner could wait on it before returning, silently
reintroducing the exact per-interaction latency User Story 2 exists to
prevent — and this would only surface as "Continuity feels slow sometimes,"
not as a test failure. Mitigation: `test_fail_open.py` and a dedicated manual
timing check in `quickstart.md` are the two closest proxies available
pre-release; a real-runtime timing measurement is called out as a required
post-implementation follow-up (the spec's own SC-006 already defers a
quantitative latency threshold to post-MVP measurement).

**What was rejected, and why?**
- *Bash for the writer/selector logic* — this plan previously chose Bash,
  reasoning (in an earlier revision) that Python would be a new runtime
  dependency the constitution does not clearly permit. That reasoning was
  never actually confirmed with the user — the constitution's "no Go or
  other standalone runtime" constraint was read as also excluding Python by
  default, without a corresponding [NEEDS CLARIFICATION] entry, and stated as
  decided fact. The user has since confirmed Python is required for this
  project and that Python is already a precondition for running Claude Code
  hooks in this environment, so it is not in fact a *new* dependency.
  `research.md` R1 currently documents the old (Bash-favoring) reasoning and
  needs a follow-up revision to reflect this; it is not corrected as part of
  this plan update because the instruction driving this revision was scoped
  to the plan, not to every downstream artifact (`research.md`, `tasks.md`,
  `data-model.md`, `contracts/*.md`, `quickstart.md`, and the repo's own
  `CLAUDE.md` all still describe a Bash implementation and need a matching
  pass).
- *`flock` for locking* — rejected because it is not part of base macOS
  (BSD userland ships no `flock` binary by default) and, more fundamentally,
  because Python's own `os.mkdir()` gives the same atomicity guarantee
  without shelling out to any external binary at all. See research.md R2
  (also written against the old Bash framing; same follow-up note applies).
- *An embedded key-value store (e.g., a single SQLite file) for the
  session-start index* — rejected even though SQLite ships in Python's own
  standard library (`sqlite3`), because Q2's answer explicitly scopes the
  MVP to file-based selection without an embedded store, and because it
  would reintroduce exactly the "what counts as a database" ambiguity Q2 was
  written to close. Revisit only if pure file-based bounding is measured to
  be insufficient post-MVP, per Q2/Q6's own deferred follow-up. See
  research.md R3.
- *A single undifferentiated `.continuity/log.md`* instead of four purpose-
  named durable files — rejected because Q6 explicitly answers with four
  named files (`state.md`, `decisions.md`, `tasks.md`, `learnings.md`), and a
  single log would make FR-004's provenance requirement (category +
  timestamp per entry) harder to satisfy cleanly and would make bounding
  (FR-005) require parsing rather than a per-file line budget.
- *`pytest`* for the test suite — rejected per SC-005's "exactly one new
  dependency: the plugin itself"; even as a dev-only dependency it is
  unnecessary weight when stdlib `unittest` fully covers this feature's
  logic. (Supersedes the earlier plan's equivalent rejection of `bats-core`;
  see research.md R6, which needs the same follow-up retargeting noted
  above.)
- *A dedicated `constraints.md` file* for the Constraint entity — rejected
  because Q6 names exactly four durable files and does not include one for
  constraints; constraints are folded into `state.md` under a `##
  Constraints` heading instead (see data-model.md).
