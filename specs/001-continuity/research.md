# Phase 0 Research: Continuity

Every `NEEDS CLARIFICATION` in the spec was already resolved by the intent
doc's answered open questions (Q1–Q10) before this plan was written, so this
research covers the remaining technology and design choices plan.md's
Technical Context depends on, plus the rejected alternatives referenced from
plan.md's Risks & Self-Review.

## R1 — Implementation language: Bash + coreutils vs. Python

- **Decision**: POSIX-compatible Bash (bash 3.2+) and standard coreutils
  only. No Python, Node, or Go.
- **Rationale**: The constitution's Additional Constraints (sourced from the
  intent doc) require "no Go or another standalone runtime for the MVP."
  Python and Node are more commonly preinstalled than Go, but they are still
  runtimes distinct from the shell Claude Code's own hook mechanism already
  invokes to run a hook `command`. Bash is the one runtime guaranteed present
  on every platform Claude Code's plugin hooks already execute on, because
  the hook runner itself must already be able to spawn a shell process to run
  the hook `command` string. Choosing Bash means Continuity adds zero new
  runtime requirements beyond what installing *any* Claude Code plugin with a
  hook already implies — directly satisfying SC-005 ("exactly one new
  dependency: the plugin itself").
- **Alternatives considered**: Python 3 stdlib-only (rejected — not
  guaranteed present on every machine Claude Code runs on, and the intent
  doc's constraint reads as "no *additional* runtime," which Python would be
  relative to the shell); Go (explicitly out of scope per the intent doc).

## R2 — Advisory locking: `mkdir` vs. `flock`

- **Decision**: A lock is a directory (`.continuity/.lock`), created with
  plain `mkdir`. `mkdir` either succeeds or fails atomically on every POSIX
  filesystem — there is no separate "check then create" race window.
- **Rationale**: `flock(1)` is a Linux util-linux tool; stock macOS (BSD
  userland) does not ship it, so relying on it would either require Continuity
  to install something (violating "no separate server process" in spirit, and
  definitely violating "adds exactly one new dependency") or maintain two
  platform-specific code paths. `mkdir`-based locking is a well-known POSIX
  idiom precisely because `mkdir`'s atomicity is guaranteed by the filesystem,
  not by a helper binary.
- **Design detail — stale-lock breaking**: A lock older than a short
  threshold (proposed: 10 seconds — long enough for any single write, short
  enough that a crashed process cannot wedge Continuity indefinitely) is
  treated as abandoned and removed before retrying. This directly answers Q5's
  "if the lock is unavailable, retry briefly and then fail gracefully" by
  giving "briefly" a concrete number, and prevents the one scenario `mkdir`
  locking cannot self-heal from (a process that dies holding the lock).
- **Alternatives considered**: `flock` (rejected, not portably available);
  a PID file with `kill -0` liveness checking (rejected — more complex, and
  still needs a mkdir-style atomic claim underneath it, so it would not
  replace `mkdir`, only add a second mechanism on top of it for a marginal
  benefit the stale-timeout already covers).

## R3 — Session-start selection: flat files vs. an embedded store

- **Decision**: Plain per-file line/byte budgets computed at read time —
  most-recent-first for `tasks.md`/`sessions/*.md`, whole-file-if-under-budget
  for `state.md`/`decisions.md`/`learnings.md`, with the total capped near
  the ~100–200 line / ~5–10 KB soft target from Q2. No index, no embedded
  database.
- **Rationale**: Q2's own answer explicitly scopes the MVP to a heuristic,
  non-database, non-embeddings selection method, and flags that the
  file-based approach should be re-measured after the MVP ships if relevance
  quality degrades. Introducing an embedded store now (even one that is not a
  "database installation" in the traditional sense, like a single SQLite
  file) would preempt that explicitly deferred decision and add a query layer
  this feature does not yet need.
- **Alternatives considered**: SQLite as a bounded index over the durable
  files (rejected for now — see above; revisit only if Q2/Q6's own
  follow-up measurement shows plain files are insufficient); an
  embeddings/relevance model (explicitly out of scope per Q2).

## R4 — Detached background writer mechanism

- **Decision**: Each triggering hook script (`capture-trigger.sh`,
  `session-end.sh`, the checkpoint command's target) launches
  `lib/write_memory.sh` with `nohup ... >/dev/null 2>&1 & disown`, then exits
  immediately. `write_memory.sh` performs exactly one consolidation pass and
  exits — it never loops, never binds a socket, never listens for further
  events.
- **Rationale**: This is the literal shape Q3's answer describes
  ("fire-and-forget asynchronous background processing... a separate
  background process after the hook returns"), and it is what the
  constitution's note on the Q3 tension asks the plan to make precise: the
  boundary between "a detached one-shot background task" (in scope) and "a
  standalone server process" (out of scope) is that the process *always*
  terminates after one unit of work and *never* accepts new work while
  running. `nohup`+`disown` detaches the process from the parent shell's job
  table and from `SIGHUP` on parent exit, so the hook process exiting does not
  kill the writer, and the writer completing does not leave anything
  listening.
- **Alternatives considered**: A persistent daemon process that the first
  hook invocation starts and later invocations message (rejected — this is
  exactly the "small persistent server" shape the constitution's Q3 note
  warns is out of scope); `setsid` for full session detachment (considered
  equivalent in effect to `nohup`+`disown` for this use case; either is
  acceptable, `nohup`+`disown` chosen as the more universally available
  built-in shell idiom without depending on `setsid`'s presence on macOS).

## R5 — Secret-pattern gate before persisting

- **Decision**: `lib/secret_scan.sh` runs a small, fixed set of regex checks
  (AWS-style access key IDs, generic `key`/`token`/`secret`/`password`
  assignment patterns, PEM private-key headers, long high-entropy hex/base64
  runs above a length threshold) over any content about to be written to
  `state.md`, `decisions.md`, `tasks.md`, or `learnings.md`. A match blocks
  that specific line from being written, and logs a redacted (pattern-name
  only, never the matched text) note to `errors.log`.
- **Rationale**: The spec's Concerns section flags that Q1's git-tracked-by-
  default answer, combined with no required content screening, lets a secret
  enter permanent shared history before a developer notices. This is
  explicitly called out as a decision for the plan stage. A regex gate is a
  mitigation consistent with every other constraint here — no network call,
  no new dependency, adds negligible latency to an already-async write path —
  while not overselling it as a guarantee.
- **Alternatives considered**: No screening at all, relying solely on the
  documented `.gitignore` opt-out (rejected — leaves the gap the Concerns
  section explicitly flags unaddressed); shelling out to a dedicated secret
  scanner like `gitleaks` (rejected for the MVP — adds an external dependency
  this toolkit's own review suite treats as something to *detect*, not
  *require*, and the constitution's zero-new-dependency posture argues the
  same way here).

## R6 — Test harness: plain Bash vs. `bats-core`

- **Decision**: Plain Bash scripts (`tests/test_*.sh`) using a minimal
  `assert_eq`/`assert_ok` pair of shell functions in `tests/run_tests.sh`,
  with no external test framework.
- **Rationale**: `bats-core` is a well-regarded Bash test framework, but it
  is a dependency Continuity's own contributors would need to install that
  the shipped plugin itself does not need — for a test surface this small
  (roughly 8 modules, each with a handful of straightforward
  input/output/exit-code assertions), plain Bash fully covers the need. This
  follows the same "fewest dependencies, standard tools first" reasoning
  applied everywhere else in this plan, applied here to the dev-only tooling
  rather than the shipped product.
- **Alternatives considered**: `bats-core` (rejected, dependency for
  marginal ergonomic gain at this scale); `shunit2` (same reasoning,
  rejected).

## R7 — Claude Code plugin/hook surface this design relies on

- **Decision**: The plugin registers three hook events —
  `SessionStart` (load context), `PostToolUse` (detect a meaningful-change
  signal after an `Edit`/`Write`/`MultiEdit`/`Bash` tool call), and
  `SessionEnd` (final checkpoint) — plus one custom slash command
  (`/continuity-checkpoint`) for an explicit checkpoint (FR-008's "explicit
  checkpoint" trigger). Hook registration lives in `hooks/hooks.json`
  alongside the plugin manifest at `.claude-plugin/plugin.json`, per Claude
  Code's plugin format; each hook command is a shell script invoked with the
  plugin's own root available via `${CLAUDE_PLUGIN_ROOT}`.
- **Rationale**: This is the smallest hook surface that covers every trigger
  FR-008/FR-009 requires (file changes and git diffs surface through
  `PostToolUse` on `Edit`/`Write`/`MultiEdit`/`Bash`; `SessionEnd` is
  required directly; "an explicit checkpoint" maps most naturally onto a
  user- or Claude-invocable slash command) without adding a hook event this
  feature has no use for.
- **Risk carried forward**: The exact JSON shape of a `PostToolUse`/
  `SessionStart`/`SessionEnd` hook's stdin payload and expected stdout
  contract is asserted by `contracts/hook-io-contract.md` and exercised in
  the integration tests by feeding hook scripts a crafted payload directly —
  but this has not been validated against a live Claude Code runtime. This is
  called out explicitly in plan.md's Risks & Self-Review and must be a first
  manual check once implementation starts (see `quickstart.md`).
