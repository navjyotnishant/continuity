---

description: "Task list template for feature implementation"
---

# Tasks: Continuity

**Input**: Design documents from `/specs/001-continuity/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/,
quickstart.md (all present)

**Tests**: Included — plan.md's Testing Strategy explicitly requests a plain-
Bash unit + integration suite (no test framework dependency, per research.md
R6).

**Organization**: Tasks are grouped by user story per spec.md's three
stories (US1, US2 — both P1 — and US3, P2). Every task in Phase 2 onward
touches the small, fixed file set plan.md's Structure Decision describes;
each story phase below states which *property* of that shared file set it
adds and proves, so stories stay independently testable even though they
are not independent files.

## Format: `[ID] [P?] [HUMAN?] [Story] Description`

Every task line is followed by an indented `Done when: <checkable
condition>` line. `[HUMAN]` marks a task no agent can do (installing into a
live Claude Code runtime, judging subjective feel, publishing a marketplace
listing).

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1/US2/US3)
- Every task names its exact file path(s)

## Path Conventions

Single-project, shell-only layout (plan.md → Project Structure). All paths
below are repository-root-relative.

---

## Phase 1: Setup

**Purpose**: Repository scaffolding for the plugin tree.

- [ ] T001 Create the plugin directory tree: `.claude-plugin/`, `hooks/`,
  `commands/`, `lib/`, `templates/`, `tests/`, and `docs/` (if not already
  present) at the repository root.
  Done when: all seven directories exist (empty is fine) and `git status`
  shows no unexpected files created.
- [ ] T002 [P] Create `lib/common.sh` with: a function to resolve the
  project's `.continuity/` path from a given `cwd` argument, a
  `continuity_log <operation> <failure-kind> <detail>` function that appends
  a scrubbed line to `.continuity/errors.log` per
  `contracts/file-format-contract.md`'s `errors.log` format (and silently
  no-ops if that append itself fails, per data-model.md's noted exception),
  and a function to read `retention_days`/`git_tracked` out of
  `metadata.json` (defaulting to 60 / true if the file is absent or
  unparseable).
  Done when: `lib/common.sh` defines all three functions and
  `tests/test_common.sh` (T003) passes.
- [ ] T003 [P] Create `tests/run_tests.sh`: a minimal harness defining
  `assert_eq expected actual msg` and `assert_ok "$?" msg` (or equivalent),
  that discovers and runs every `tests/test_*.sh` file and exits non-zero if
  any assertion fails; and `tests/test_common.sh` covering `lib/common.sh`'s
  three functions (path resolution against a fixture project dir, a log
  append, a default-config read against a missing `metadata.json`).
  Done when: `bash tests/run_tests.sh` runs and reports `test_common.sh`
  passing.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The primitives every later hook and the write path depend on.
Plan.md orders this first because a bug here corrupts state for *every*
future session on a project, not just the triggering one.

**⚠️ CRITICAL**: No user-story work begins until this phase is complete.

- [ ] T004 [P] Create `lib/atomic_write.sh` implementing the write-to-
  `<target>.tmp.<pid>`-then-`mv` pattern from
  `contracts/file-format-contract.md` → Atomicity, refusing to overwrite
  `<target>` with empty content (data-model.md's State Note validation
  rule).
  Done when: `tests/test_atomic_write.sh` (T009) passes.
- [ ] T005 [P] Create `lib/lock.sh` with `lock_acquire <path> [timeout]` and
  `lock_release <path>` using `mkdir <path>/.lock` as the atomic claim,
  retrying briefly on contention, and breaking (removing) a lock directory
  older than 10 seconds before retrying once more, per research.md R2.
  Done when: `tests/test_lock.sh` (T010) passes.
- [ ] T006 [P] Create `lib/secret_scan.sh` with `secret_scan_line <text>`
  returning non-zero (and the matched pattern name on stdout) for an
  AWS-style access key, a `key|token|secret|password=` assignment pattern, a
  PEM private-key header, or a long high-entropy hex/base64 run, per
  research.md R5; zero for ordinary text.
  Done when: `tests/test_secret_scan.sh` (T011) passes.
- [ ] T007 Create `lib/migrate.sh` with `metadata_ensure <continuity-dir>`
  (creates `metadata.json` from `templates/metadata.json.tmpl` if absent)
  and `metadata_check_and_migrate <continuity-dir>` implementing
  `contracts/file-format-contract.md`'s `metadata.json` compatibility rules
  (migrate one version back, fail open and untouched on an unsupported newer
  version). Depends on T002 (uses `common.sh` logging) and T004 (uses
  atomic writes for the migrated files).
  Done when: `tests/test_migrate.sh` (T012) passes.
- [ ] T008 [P] Create the five seed templates: `templates/state.md.tmpl`,
  `templates/decisions.md.tmpl`, `templates/tasks.md.tmpl`,
  `templates/learnings.md.tmpl`, `templates/metadata.json.tmpl`, each
  matching the field shapes in data-model.md (state.md includes an empty
  `## Constraints` section; learnings.md includes an empty `##
  Conventions` section; metadata.json.tmpl matches data-model.md's
  `metadata.json` example with `schema_version: "1.0"`).
  Done when: all five files exist and `metadata.json.tmpl` is valid JSON
  (`python3 -m json.tool < templates/metadata.json.tmpl` or equivalent
  exits 0 — used only as a validation check here, not a runtime
  dependency).
- [ ] T009 [P] Create `tests/test_atomic_write.sh`: writes a file, verifies
  its content; simulates a crash by writing the `.tmp.<pid>` path and
  never renaming, then asserts the original target is unchanged and a
  `.tmp.*` file is left behind (setup for T032's sweep).
  Done when: `bash tests/test_atomic_write.sh` exits 0 once T004 exists.
- [ ] T010 [P] Create `tests/test_lock.sh`: two backgrounded subshells race
  `lock_acquire` on the same path — asserts exactly one returns
  immediately and the other either succeeds after the first releases or
  times out and returns non-zero; asserts a lock dir older than 10 seconds
  (fabricated with `touch -t`) is broken and re-acquired.
  Done when: `bash tests/test_lock.sh` exits 0 once T005 exists.
- [ ] T011 [P] Create `tests/test_secret_scan.sh`: asserts each of the
  four secret-shaped fixtures from research.md R5 is rejected, and three
  ordinary-prose fixtures are accepted.
  Done when: `bash tests/test_secret_scan.sh` exits 0 once T006 exists.
- [ ] T012 Create `tests/test_migrate.sh`: asserts a file at the current
  schema version is unchanged; a file at the previous version gains the
  current `schema_version` after migration; a file at an unsupported newer
  version is byte-for-byte unchanged and `errors.log` gains an
  `unsupported-schema` line.
  Done when: `bash tests/test_migrate.sh` exits 0 once T007 exists.

**Checkpoint**: Foundation ready — every later phase builds directly on
`lib/atomic_write.sh`, `lib/lock.sh`, `lib/secret_scan.sh`, `lib/migrate.sh`,
and the seed templates.

---

## Phase 3: User Story 1 - Resume a project without re-explaining it (Priority: P1) 🎯 MVP

**Goal**: A new session on a project with prior Continuity history opens
with the still-relevant decisions, tasks, constraints, and last handoff
already in context, without the developer restating them.

**Independent Test**: Work a session to a decision + an unfinished task,
end it, start a new session, confirm the opening context includes both
(quickstart.md Scenario 1).

**Acceptance criteria** (from spec.md US1 scenarios 1–3):
1. **Given** a project with prior Continuity history under `.continuity/`,
   **When** a new session starts, **Then** the opening context includes the
   still-relevant decisions, active tasks, constraints, and the most recent
   handoff, without the developer asking for them.
2. **Given** a decision recorded in a previous session, **When** the
   developer asks a question depending on it in the new session, **Then**
   Claude answers consistently with the recorded decision.
3. **Given** a project with no prior Continuity session, **When** a new
   session starts, **Then** it proceeds normally with no continuity context
   injected and no error.

### Tests for User Story 1

- [ ] T013 [P] [US1] Create `tests/test_select_context.sh`: builds a fixture
  `.continuity/` store exceeding the ~100–200 line target and asserts the
  output of `lib/select_context.sh` stays within it; builds an empty/absent
  store and asserts empty output with no error (covers FR-005/FR-007).
- [ ] T014 [P] [US1] Create `tests/test_write_memory_basic.sh`: invokes
  `lib/write_memory.sh` against a fixture `cwd` with a synthetic
  `file-change` trigger and a decision-shaped input, and asserts
  `decisions.md` gains a well-formed entry (per data-model.md's Decision
  Record fields) and a new file appears under `.continuity/sessions/`.

### Implementation for User Story 1

- [ ] T015 [US1] Create `lib/select_context.sh` implementing
  `select_context <continuity-dir>`: reads `state.md` (whole file if under
  budget), `decisions.md`/`tasks.md`/`learnings.md` (most-recent-first,
  `active`/`blocked` tasks prioritized over `done`, per data-model.md's
  Task Entry rule), and the most recent file under `sessions/`; bounds the
  total to the ~100–200 line / ~5–10 KB soft target (Q2); wraps the result
  in the exact labeled block from `contracts/hook-io-contract.md`'s
  `SessionStart` section, omitting empty sections. Depends on T007
  (`metadata_check_and_migrate` gates this) and T004 (reads via the same
  file-format assumptions `atomic_write.sh` guarantees).
  Done when: `tests/test_select_context.sh` (T013) passes.
- [ ] T016 [US1] Create `hooks/session-start.sh`: reads the stdin JSON
  payload, resolves `.continuity/` from `cwd`, calls
  `metadata_check_and_migrate` then `select_context`, and emits the
  `hookSpecificOutput.additionalContext` JSON exactly as specified in
  `contracts/hook-io-contract.md` → `SessionStart`; on any internal error,
  logs via `common.sh` and emits no `additionalContext` (fail open).
  Done when: piping a fixture stdin payload into
  `bash hooks/session-start.sh` against a populated fixture project prints
  valid JSON containing the labeled context block, and against an absent
  `.continuity/` prints valid JSON with no `additionalContext` key.
- [ ] T017 [US1] Create `lib/write_memory.sh` implementing
  `write_memory <cwd> <trigger-kind>`: acquires the store lock
  (`lib/lock.sh`), reads the latest durable files, determines what new
  decision/task/learning/state content (if any) the current interaction
  produced, runs `secret_scan_line` over every new line before writing (R5;
  a rejected line is dropped and logged as `secret-blocked`, the rest of the
  entry still written), appends/updates the relevant durable file(s) via
  `atomic_write.sh`, writes a `sessions/<timestamp>-<pid>.md` handoff file
  (data-model.md's Session Handoff fields, `trigger` set to the passed-in
  kind), and releases the lock; produces no file changes at all if there is
  nothing meaningful to persist (FR-011). Depends on T004, T005, T006, T007.
  Done when: `tests/test_write_memory_basic.sh` (T014) passes.
- [ ] T018 [US1] [P] Create `commands/continuity-checkpoint.md`: a slash
  command that synchronously invokes
  `lib/write_memory.sh "$CLAUDE_PROJECT_DIR" explicit-checkpoint` (or the
  equivalent Claude Code plugin variable for the project root) and reports
  the result per `contracts/hook-io-contract.md`'s checkpoint-command
  output shape.
  Done when: running the command against a fixture project with pending
  content produces a new `sessions/*.md` file and a confirmation message;
  against a fixture project with nothing new, produces a "nothing to
  checkpoint" message and no new file.
- [ ] T019 [US1] Create `hooks/capture-trigger.sh` implementing the
  `PostToolUse` classification from `contracts/hook-io-contract.md`
  (meaningful `Edit`/`Write`/`MultiEdit` diff, or a `git`-touching `Bash`
  call with a non-whitespace `git diff --stat`); on a meaningful signal,
  launches `lib/write_memory.sh "$cwd" <trigger-kind>` via
  `nohup ... >/dev/null 2>&1 & disown` and exits; on a non-meaningful
  signal, exits with no output and nothing logged (FR-011). Depends on
  T017.
  Done when: fed a fixture whitespace-only-diff payload, no
  `.continuity/` file changes and no `errors.log` line result; fed a
  fixture non-trivial-diff payload, a `.continuity/sessions/*.md` file
  eventually appears (poll with a short timeout in the test) while
  `hooks/capture-trigger.sh` itself returns in under 100ms.

**Checkpoint**: User Story 1 is fully functional — a project accumulates
decisions/tasks/handoffs and a new session's `SessionStart` hook surfaces
them, independently of Stories 2 and 3.

---

## Phase 4: User Story 2 - Never notice Continuity is running (Priority: P1)

**Goal**: No interactive turn is perceptibly delayed by a Continuity memory
write or by any per-interaction LLM call.

**Independent Test**: Time a representative sequence of turns with and
without Continuity installed and confirm no turn is measurably delayed;
confirm no background writer is ever waited on (quickstart.md Scenario 2).

**Acceptance criteria** (from spec.md US2 scenarios 1–3):
1. **Given** Continuity is active, **When** the developer sends a message
   that would trigger a memory-write signal, **Then** Claude's response is
   not delayed waiting for the write to finish.
2. **Given** a long session with many background writes, **When** those
   writes occur, **Then** no individual turn incurs an additional LLM call
   solely to summarize or persist memory.
3. **Given** a new session is starting, **When** Continuity loads its
   bounded context, **Then** the added session-start time is not
   perceptible.

### Tests for User Story 2

- [ ] T020 [P] [US2] Create `tests/test_detach.sh`: invokes
  `hooks/capture-trigger.sh` with a fixture `write_memory.sh` stub that
  sleeps for 2 seconds, and asserts the hook script itself returns in under
  200ms (proving the writer is detached, not awaited) — the timing margin
  the real hook needs to hold well inside per plan.md's Performance Goals.
- [ ] T021 [P] [US2] Extend `tests/test_write_memory_basic.sh` (T014) or add
  `tests/test_no_llm_call.sh` asserting `lib/write_memory.sh` and
  `hooks/session-start.sh` invoke no network call and no external process
  other than coreutils/git (grep the scripts for the absence of `curl`,
  `curl`-like invocations, or any API-call pattern — a static check standing
  in for "no LLM call," since neither script has network access to make one
  per the Q7 permission boundary).

### Implementation for User Story 2

- [ ] T022 [US2] Verify and, if needed, correct the detachment idiom in
  `hooks/capture-trigger.sh` (T019) and add the identical
  `nohup ... & disown` launch to `hooks/session-end.sh` (new file,
  implementing `contracts/hook-io-contract.md` → `SessionEnd`: reads stdin,
  unconditionally launches `lib/write_memory.sh "$cwd" session-end`
  detached, exits with no output).
  Done when: `tests/test_detach.sh` (T020) passes for both
  `capture-trigger.sh` and `session-end.sh`.
- [ ] T023 [US2] [P] Create `hooks/hooks.json` registering `SessionStart` →
  `hooks/session-start.sh`, `PostToolUse` (matcher
  `Edit|Write|MultiEdit|Bash`) → `hooks/capture-trigger.sh`, and
  `SessionEnd` → `hooks/session-end.sh`, using `${CLAUDE_PLUGIN_ROOT}` for
  every command path per research.md R7.
  Done when: the JSON is valid (`python3 -m json.tool` or equivalent exits
  0) and every `command` path resolves under `${CLAUDE_PLUGIN_ROOT}`.
- [ ] T024 [HUMAN] [US2] Install the plugin into a real Claude Code session
  (per whatever install flow T035's marketplace listing provides) and run
  quickstart.md Scenario 2's timed comparison for at least 10 interactive
  turns, recording the millisecond deltas.
  Done when: the recorded deltas show no turn with Continuity installed is
  consistently slower than its counterpart without it, and the numbers are
  written into `docs/install.md` or a follow-up note referenced from it.

**Checkpoint**: User Stories 1 AND 2 both hold — the pipeline built in
Phase 3 now provably never blocks the interactive turn that triggered it.

---

## Phase 5: User Story 3 - Keep working when memory breaks (Priority: P2)

**Goal**: A missing, corrupted, or unwritable `.continuity/` store never
produces a crash, a blocking error, or degraded interactive behavior.

**Independent Test**: Corrupt/remove `.continuity/` content in each of the
ways spec.md's US3 describes and confirm sessions still start/continue
normally, with the failure only visible in `errors.log`
(quickstart.md Scenario 3).

**Acceptance criteria** (from spec.md US3 scenarios 1–3):
1. **Given** a corrupted `.continuity/` file, **When** a session starts and
   loads context, **Then** the session starts normally with that file's
   content omitted, and the corruption is logged locally, not surfaced as a
   blocking error.
2. **Given** a background write fails partway, **When** the failure occurs,
   **Then** the interactive session is unaffected and no partially-written
   file is left in a broken state.
3. **Given** `.continuity/` does not exist, **When** a session starts or a
   trigger fires, **Then** Continuity treats this as "no history yet" or
   creates the directory as needed, without error.

### Tests for User Story 3

- [ ] T025 [P] [US3] Create `tests/test_fail_open.sh`: for each of (a)
  missing `.continuity/`, (b) a corrupted `decisions.md` (invalid entry —
  missing `captured_at`), (c) an unreadable `state.md` (`chmod 000`), and
  (d) a `.continuity/` directory itself `chmod 000` during a write attempt
  — asserts `hooks/session-start.sh` and `hooks/capture-trigger.sh` /
  `lib/write_memory.sh` each still exit successfully, every *other* valid
  file still loads where applicable, and an appropriately-kinded line
  appears in `errors.log` (except case (d), where the log write may itself
  silently fail, per data-model.md's noted exception).

### Implementation for User Story 3

- [ ] T026 [US3] Add per-entry fail-open parsing to `lib/select_context.sh`
  (T015): a malformed entry in `decisions.md`/`tasks.md`/`learnings.md` (per
  `contracts/file-format-contract.md`'s entry-validity rule) is skipped and
  logged, not fatal to the rest of the file; a `state.md` failing its
  `updated_at` check is treated as if `state.md` were absent, logged as
  `corrupted`.
  Done when: `tests/test_fail_open.sh` (T025) cases (a) and (b) pass.
- [ ] T027 [US3] Add read/permission error handling to
  `lib/select_context.sh` and `hooks/session-start.sh`: an unreadable file
  is caught (not an uncaught shell error), logged as `unreadable`, and
  treated as absent for that file only.
  Done when: `tests/test_fail_open.sh` (T025) case (c) passes.
- [ ] T028 [US3] Add write-failure handling to `lib/write_memory.sh` and
  `lib/lock.sh`: a failed `mkdir` (lock), a failed `mv` (atomic write), or
  an unwritable `.continuity/` directory causes `write_memory.sh` to abort
  that run cleanly (no partial file — `atomic_write.sh`'s temp-then-rename
  already guarantees this per T004/T009), log `write-failed` or
  `lock-unavailable` best-effort, and return — never propagating an error
  to the calling hook.
  Done when: `tests/test_fail_open.sh` (T025) case (d) passes, and
  `tests/test_atomic_write.sh` (T009)'s crash-simulation case still holds
  (no regression).
- [ ] T029 [US3] Add `.continuity/` auto-creation to `lib/write_memory.sh`:
  if `.continuity/` is absent when a trigger fires, create it and seed it
  from `templates/*.tmpl` (T008) before proceeding, rather than failing.
  Done when: running `lib/write_memory.sh` against a `cwd` with no
  `.continuity/` produces a populated, valid store with no error.

**Checkpoint**: All three user stories are independently functional — the
MVP (US1) works, is provably non-blocking (US2), and degrades safely under
every documented failure mode (US3).

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Retention, packaging, and documentation — none of this is
required for any single user story's acceptance criteria, but all of it is
required before the plugin ships.

- [ ] T030 [P] Create `lib/retention.sh` implementing
  `retention_prune <continuity-dir>`: deletes any file under `sessions/`
  older than `retention_days` (parsed from the filename per
  `contracts/file-format-contract.md`, not file mtime), trims `errors.log`
  lines older than the same window, and sweeps any `.tmp.*` file older than
  one hour (crash debris per the Atomicity contract); called from the end
  of a successful `lib/write_memory.sh` run (plan.md's Implementation Order
  step 4 — piggybacks on an already-scheduled background process).
  Done when: `tests/test_retention.sh` (T031) passes.
- [ ] T031 [P] Create `tests/test_retention.sh`: fabricates a `sessions/`
  file older than the retention window and one inside it, asserts only the
  older one is pruned; asserts durable files (`state.md` etc.) are never
  touched regardless of age; asserts a fabricated stale `.tmp.*` file is
  swept.
- [ ] T032 Wire `retention_prune` into the end of `lib/write_memory.sh`
  (T017)'s successful path.
  Done when: `tests/test_write_memory_basic.sh` (T014) still passes and a
  fabricated stale `sessions/` file is gone after a `write_memory.sh` run
  in the same test fixture.
- [ ] T033 [P] Create `.claude-plugin/plugin.json`: the plugin manifest
  (name `continuity`, version, description, and the hooks entrypoint
  pointing at `hooks/hooks.json`), per Claude Code's plugin manifest format.
  Done when: the file is valid JSON and names every hook script T016, T019,
  and T022 create.
- [ ] T034 [P] Create `.claude-plugin/marketplace.json`: lists this
  repository as a GitHub-hosted marketplace source for the `continuity`
  plugin (FR-015).
  Done when: the file is valid JSON and matches whatever schema Claude
  Code's marketplace format requires at implementation time (verify against
  current Claude Code plugin docs before finalizing field names).
- [ ] T035 [HUMAN] Publish/register this repository as an installable
  marketplace source and confirm a real Claude Code session can install the
  `continuity` plugin from it.
  Done when: a plugin-install command against this repository's
  marketplace succeeds in a live Claude Code session and the plugin appears
  active.
- [ ] T036 [P] Create `docs/install.md`: documents that `.continuity/` is
  git-tracked by default (Q1), gives the exact `.gitignore` + (if needed)
  `git rm -r --cached .continuity/` steps for the opt-out (FR-020), states
  plainly that `lib/secret_scan.sh` is a mitigation and not a guarantee
  (per plan.md's Risks), and documents `retention_days`/`git_tracked` as
  user-editable fields in `metadata.json`.
  Done when: following the documented opt-out steps against a fixture repo
  produces the outcome quickstart.md Scenario 5 describes.
- [ ] T037 [HUMAN] Run quickstart.md Scenarios 1, 3, 4, and 5 end-to-end in
  a live Claude Code session (Scenario 2 is covered by T024) and record any
  deviation from their stated "Expected" outcomes.
  Done when: all four scenarios' Expected outcomes are confirmed, or any
  deviation is filed as a follow-up task before this feature is marked
  done.
- [ ] T038 Run `bash tests/run_tests.sh` and confirm every test file from
  Phases 1–6 passes together (not just individually), and re-run
  `contracts/hook-io-contract.md`'s and `contracts/file-format-contract.md`'s
  rules as a final read-through checklist against the finished `hooks/*.sh`
  and `lib/*.sh` files.
  Done when: `bash tests/run_tests.sh` exits 0 and the checklist read-
  through finds no deviation from either contract file.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS every user story.
- **User Story 1 (Phase 3)**: Depends on Phase 2. No dependency on US2/US3.
- **User Story 2 (Phase 4)**: Depends on Phase 2 **and** on US1's
  `hooks/capture-trigger.sh` (T019) and `lib/write_memory.sh` (T017)
  already existing — T022 modifies/verifies T019 and adds
  `hooks/session-end.sh` alongside it. This is the one story-to-story
  dependency in this feature, and it exists because US2 is a property
  *of* US1's write path, not a separate code path (plan.md's Structure
  Decision).
- **User Story 3 (Phase 5)**: Depends on Phase 2 and on US1's
  `lib/select_context.sh` (T015), `hooks/session-start.sh` (T016), and
  `lib/write_memory.sh` (T017) already existing — it adds defensive
  handling to those same files rather than creating new ones.
- **Polish (Phase 6)**: Depends on Phases 3–5 being complete.

### User Story Dependencies

- **US1 (P1)**: No dependency on US2/US3 — it is buildable and testable
  (quickstart Scenario 1) on its own once Phase 2 is done.
- **US2 (P1)**: Depends on US1's write-path files existing (see above);
  otherwise independently testable (quickstart Scenario 2) once T022–T023
  land.
- **US3 (P2)**: Depends on US1's read/write-path files existing (see
  above); otherwise independently testable (quickstart Scenario 3) once
  T026–T029 land.

### Within Each Phase

- Tests are written before the implementation task that makes them pass
  (T013/T014 before T015/T017; T020/T021 before T022; T025 before
  T026–T029; T031 before T032) and must fail first.
- `[P]`-marked tasks touch disjoint files and have no completed-task
  dependency within their phase — safe to parallelize.

### Parallel Opportunities

- Phase 1: T002 and T003 in parallel.
- Phase 2: T004, T005, T006, T008 in parallel (T007 depends on T002/T004,
  so it waits); T009, T010, T011 in parallel once their respective
  implementation task lands; T012 waits on T007.
- Phase 3: T013 and T014 in parallel; T018 in parallel with T015–T017 (own
  file, only depends on T017 existing before it's meaningful to test, not
  to write).
- Phase 4: T020 and T021 in parallel; T023 in parallel with T022.
- Phase 5: T025 alone (it is the only test file, exercising all of
  T026–T029); T026 and T027 in parallel (disjoint concerns within the same
  file — coordinate on non-overlapping edits or serialize if that's
  simpler); T028 and T029 in parallel with each other.
- Phase 6: T030/T031, T033/T034, T036 all in parallel; T032 waits on T030;
  T035 waits on T033/T034; T037 waits on all prior phases; T038 last.

---

## Parallel Example: Phase 2 (Foundational)

```bash
# Launch together — disjoint files, no shared state:
Task: "Create lib/atomic_write.sh (T004)"
Task: "Create lib/lock.sh (T005)"
Task: "Create lib/secret_scan.sh (T006)"
Task: "Create the five templates/*.tmpl seed files (T008)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories).
3. Complete Phase 3: User Story 1.
4. **STOP and VALIDATE**: run quickstart.md Scenario 1 (manually, once a
   real Claude Code install is available — T024/T037 formalize this later,
   but nothing prevents a manual check right after Phase 3).
5. This is a real MVP: a project already accumulates and re-surfaces
   context, even before US2's timing guarantees are formally verified or
   US3's failure-mode hardening lands.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. Add US1 → validate independently → this is the MVP.
3. Add US2 → validate independently (timing).
4. Add US3 → validate independently (failure injection).
5. Polish (retention, packaging, docs) → ship.

### Solo-Agent Strategy

Given this feature's small, tightly-coupled file set (plan.md's Structure
Decision), a single implementer works the phases in order rather than
splitting user stories across parallel workers — Phase 4 and Phase 5 both
modify files Phase 3 creates, so working them concurrently against the same
files would conflict. The `[P]` markers inside each phase are where real
parallelism exists.

---

## Notes

- `[P]` tasks = different files, no dependencies.
- `[Story]` label maps a task to its user story for traceability into the
  tracker tree this file decomposes into.
- `[HUMAN]` tasks (T024, T035, T037) all require a live Claude Code runtime
  or a marketplace-publishing action — every one of them is called out in
  plan.md's Risks & Self-Review as the one boundary this plan's own test
  suite cannot exercise.
- Verify each test fails before implementing the task that makes it pass.
- Stop at any checkpoint to validate a story independently before
  continuing.
