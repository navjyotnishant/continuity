# Phase 0 Research: Continuity

Every `NEEDS CLARIFICATION` in the spec was already resolved by the intent
doc's answered open questions (Q1–Q10) before this plan was written, so this
research covers the remaining technology and design choices plan.md's
Technical Context depends on, plus the rejected alternatives referenced from
plan.md's Risks & Self-Review.

## R1 — Implementation language: Python vs. Bash + coreutils

- **Decision**: Python 3.9+, standard library only (Q11). No Bash, Node, or
  Go.
- **Rationale**: The constitution's Additional Constraints (sourced from the
  intent doc) require "no Go or another standalone runtime for the MVP."
  This plan previously read that constraint as also excluding Python by
  default and chose Bash on that basis — but that reading was never actually
  confirmed with the user (see plan.md's Risks → "What was rejected, and
  why" for the September 12 correction). Python is already required to run
  Claude Code hooks in this environment, so it is not in fact a *new*
  runtime the plugin introduces — it satisfies "no standalone runtime for
  the MVP" the same way Bash would have, without needing Bash's
  POSIX-portability workarounds (bash 3.2 on macOS vs. bash ≥4 on Linux;
  native Windows has no Bash at all, and this project's platform scope now
  explicitly includes native Windows per Q11). Choosing Python means
  Continuity adds zero new runtime requirements beyond what installing *any*
  Claude Code plugin with a hook already implies — directly satisfying
  SC-005 ("exactly one new dependency: the plugin itself").
- **Alternatives considered**: POSIX-compatible Bash + coreutils (rejected —
  this was the earlier decision; superseded because it does not run
  natively on Windows, and because the constraint it was trying to satisfy
  does not actually exclude Python, per the correction above); Go
  (explicitly out of scope per the intent doc); Node (rejected for the same
  "not what Claude Code hooks already require" reasoning Python's rationale
  turns on its head).

## R2 — Advisory locking: `os.mkdir()` vs. `flock`/a named mutex

- **Decision**: A lock is a directory (`.continuity/.lock`), created with
  Python's `os.mkdir()`. `os.mkdir()` either succeeds or raises
  `FileExistsError` atomically on every filesystem it runs against — there
  is no separate "check then create" race window.
- **Rationale**: `flock(1)`/`fcntl.flock()` is POSIX-only (stock macOS BSD
  userland ships no `flock` binary, and there is no equivalent at all on
  native Windows, which Q11 puts in scope); a Windows named-mutex API is the
  mirror-image problem, POSIX systems have no equivalent. Relying on either
  would mean either installing something (violating "no separate server
  process" in spirit, and definitely violating "adds exactly one new
  dependency") or maintaining two platform-specific locking code paths.
  `os.mkdir()` needs neither: it is one stdlib call, its atomicity is
  guaranteed by the filesystem/OS, not by a helper binary or a
  platform-specific API, and it behaves identically on macOS, Linux, and
  native Windows.
- **Design detail — stale-lock breaking**: A lock older than a short
  threshold (proposed: 10 seconds — long enough for any single write, short
  enough that a crashed process cannot wedge Continuity indefinitely) is
  treated as abandoned and removed before retrying. This directly answers Q5's
  "if the lock is unavailable, retry briefly and then fail gracefully" by
  giving "briefly" a concrete number, and prevents the one scenario
  `os.mkdir()` locking cannot self-heal from (a process that dies holding the
  lock).
- **Alternatives considered**: `flock`/`fcntl.flock()` (rejected, POSIX-only,
  no Windows equivalent); a Windows named-mutex API (rejected, the mirror
  problem — no POSIX equivalent, and it would mean maintaining two code
  paths instead of one); a PID file with liveness checking (`os.kill(pid, 0)`
  on POSIX has no direct Windows stdlib equivalent either — rejected as more
  complex, and it would still need an `os.mkdir()`-style atomic claim
  underneath it, so it would not replace `os.mkdir()`, only add a second
  mechanism on top of it for a marginal benefit the stale-timeout already
  covers).

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

- **Decision**: Each triggering hook script (`capture-trigger.py`,
  `session-end.py`, the checkpoint command's target) launches
  `lib/write_memory.py` with `subprocess.Popen(..., stdin=DEVNULL,
  stdout=DEVNULL, stderr=DEVNULL, close_fds=True, **detach_kwargs)`, then
  exits immediately. `detach_kwargs` branches on `os.name`:
  `{"start_new_session": True}` on POSIX (`posix`), which reparents the
  writer away from the hook process instead of leaving it a child of it;
  `{"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP |
  subprocess.DETACHED_PROCESS}` on native Windows (`nt`) — `DETACHED_PROCESS`
  gives the writer no console to inherit and `CREATE_NEW_PROCESS_GROUP` keeps
  it out of the hook process's process group. `write_memory.py` performs
  exactly one consolidation pass and exits — it never loops, never binds a
  socket, never listens for further events.
- **Rationale**: This is the literal shape Q3's answer describes
  ("fire-and-forget asynchronous background processing... a separate
  background process after the hook returns"), and it is what the
  constitution's note on the Q3 tension asks the plan to make precise: the
  boundary between "a detached one-shot background task" (in scope) and "a
  standalone server process" (out of scope) is that the process *always*
  terminates after one unit of work and *never* accepts new work while
  running. The POSIX branch is the direct equivalent of what Bash's
  `nohup ... & disown` idiom achieved (detaching from the parent's job table
  and from `SIGHUP` on parent exit); native Windows (in scope per Q11) has no
  `nohup`/`disown` equivalent at all, so the design needs both branches
  explicitly rather than punting Windows to Risks.
- **Alternatives considered**: A persistent daemon process that the first
  hook invocation starts and later invocations message (rejected — this is
  exactly the "small persistent server" shape the constitution's Q3 note
  warns is out of scope); `os.fork()` + `os.setsid()` for full session
  detachment on POSIX (rejected — `os.fork()` does not exist on Windows at
  all, so it would still need a separate Windows path, whereas
  `subprocess.Popen`'s `detach_kwargs` branches already give one API with two
  platform-specific argument sets instead of two entirely different process-
  creation calls).

## R5 — Secret-pattern gate before persisting

- **Decision**: `lib/secret_scan.py` runs a small, fixed set of `re`-based
  regex checks
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

## R6 — Test harness: stdlib `unittest` vs. `pytest`

- **Decision**: Python's standard-library `unittest` (`tests/test_*.py`),
  discovered and run via `python3 -m unittest discover -s tests`, wrapped by
  `tests/run_tests.py` for a single entry point. No external test framework.
- **Rationale**: `pytest` is a well-regarded Python test framework, but it
  is a dependency Continuity's own contributors would need to install that
  the shipped plugin itself does not need — for a test surface this small
  (roughly 8 modules, each with a handful of straightforward
  input/output/exit-code assertions), stdlib `unittest` fully covers the
  need. This follows the same "fewest dependencies, standard tools first"
  reasoning applied everywhere else in this plan, applied here to the
  dev-only tooling rather than the shipped product. (This supersedes an
  earlier revision of this research that framed the equivalent question as
  plain Bash vs. `bats-core`, back when the implementation language was
  Bash — see R1's correction.)
- **Alternatives considered**: `pytest` (rejected, dependency for marginal
  ergonomic gain at this scale — same reasoning the earlier Bash-based plan
  applied to `bats-core`); `unittest2`/other unittest backports (rejected,
  unnecessary — Python 3.9's own `unittest` already has everything this
  feature's tests need).

## R7 — Claude Code plugin/hook surface this design relies on

- **Decision**: The plugin registers three hook events —
  `SessionStart` (load context), `PostToolUse` (detect a meaningful-change
  signal after an `Edit`/`Write`/`MultiEdit`/`Bash` tool call), and
  `SessionEnd` (final checkpoint) — plus one custom slash command
  (`/continuity-checkpoint`) for an explicit checkpoint (FR-008's "explicit
  checkpoint" trigger). Hook registration lives in `hooks/hooks.json`
  alongside the plugin manifest at `.claude-plugin/plugin.json`, per Claude
  Code's plugin format; each hook command explicitly invokes
  `python3 hooks/<script>.py` (`python.exe hooks\<script>.py` on native
  Windows), never a `#!/usr/bin/env python3` shebang, with the plugin's own
  root available via `${CLAUDE_PLUGIN_ROOT}`.
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
