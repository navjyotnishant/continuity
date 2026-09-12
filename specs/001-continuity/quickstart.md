# Quickstart: Validating Continuity

These scenarios prove the feature end-to-end, in the same terms as the
spec's own Independent Tests for User Stories 1–3. Run them after
Implementation Order phases 1–5 (plan.md) are complete and the plugin is
installed in a real Claude Code session — the unit/integration test suite
(`tests/run_tests.sh`) covers the logic in isolation, but only this
quickstart exercises the real Claude Code hook runtime end-to-end (the one
gap plan.md's Risks section calls out as unautomatable pre-release).

## Prerequisites

- The plugin installed from this repo's marketplace into a Claude Code
  session (`claude plugin install continuity` or the marketplace-add flow —
  exact command per Claude Code's own plugin install docs at implementation
  time).
- A scratch git repository to test against — do **not** use this repository
  itself for the first pass, so a bad first run cannot pollute this
  project's own `.continuity/`.
- Bash available (already assumed by every target platform per plan.md).

## Scenario 1 — User Story 1: resume a project without re-explaining it

1. In the scratch repo, start a Claude Code session with Continuity
   installed.
2. Make one clearly stated decision (e.g., ask Claude to pick between two
   approaches and state which one and why) and leave one task explicitly
   unfinished (e.g., "we still need to add input validation to X").
3. Trigger at least one meaningful-change signal (edit a file, or run
   `/continuity-checkpoint` directly) and confirm a new file appears under
   `.continuity/decisions.md` and `.continuity/tasks.md` reflecting the two
   items above — `cat .continuity/decisions.md .continuity/tasks.md`.
4. End the session (close the terminal, or send whatever ends a Claude Code
   session in the environment under test).
5. Start a **brand-new** session in the same scratch repo.
6. **Expected**: the new session's opening context (visible in its first
   response, or inspectable via whatever debug/verbose mode Claude Code
   exposes for injected context) includes the decision and the unfinished
   task from step 2, labeled as Continuity context per
   `contracts/hook-io-contract.md`'s context block format — without you
   having restated either.
7. Ask a question in the new session that depends on the recorded decision.
   **Expected**: the answer is consistent with the recorded decision.

## Scenario 2 — User Story 2: never notice Continuity is running

1. In the scratch repo, time a representative sequence of ~10 interactive
   turns (a mix of questions, file edits, and a `git commit`) with
   Continuity installed. Note the wall-clock time from message-sent to
   first-token for each turn.
2. Disable or uninstall Continuity (or use a second scratch repo without
   it) and repeat the same sequence of turns.
3. **Expected**: no turn in run 1 is measurably slower than its counterpart
   in run 2 by more than normal run-to-run variance — no turn should show a
   consistent added delay attributable to Continuity. This is the
   qualitative check SC-006 defers a hard number for; record actual
   millisecond deltas here if you want to start building toward a
   quantitative threshold post-MVP.
4. **Expected**: inspecting `.continuity/errors.log` and the process list
   during step 1 shows the background writer processes exist only briefly
   and are never still running by the time the next turn starts (confirms
   research.md R4's detachment claim empirically, closing plan.md's
   riskiest-step gap).

## Scenario 3 — User Story 3: keep working when memory breaks

Run each of these independently (undo between them):

1. **Missing directory**: `rm -rf .continuity/` in the scratch repo, then
   start a new session. **Expected**: session starts normally, no error
   shown, `.continuity/` is recreated on the next write trigger.
2. **Corrupted file**: `echo "not valid" > .continuity/decisions.md` (or
   truncate it mid-entry), then start a new session. **Expected**: session
   starts normally; `state.md`/`tasks.md`/`learnings.md` content still
   loads; `errors.log` gains a `corrupted` entry for `decisions.md`; no
   user-facing error appears.
3. **Unreadable file**: `chmod 000 .continuity/state.md`, then start a new
   session. **Expected**: same as above, with an `unreadable` entry logged.
   Remember to `chmod 644` it back afterward.
4. **Write failure**: fill the disk or `chmod 000 .continuity/` itself, then
   trigger a meaningful-change signal. **Expected**: the interactive turn
   completes normally with no visible delay or error; `errors.log` gains a
   `write-failed` entry (best-effort — if `.continuity/` itself is
   unwritable, this specific log write may also fail silently, per
   data-model.md's noted exception for `errors.log`'s own failure mode).

## Scenario 4 — schema/version compatibility (Q9)

1. Hand-edit `.continuity/metadata.json`'s `schema_version` to a value one
   below the plugin's current version. Start a session.
   **Expected**: the store is migrated forward (inspect `metadata.json` —
   `schema_version` now matches current) and the session's context still
   loads.
2. Hand-edit `schema_version` to a value *above* the plugin's current
   version. Start a session. **Expected**: session starts normally, no
   continuity context is injected, `metadata.json` is left byte-for-byte
   unmodified, and `errors.log` gains an `unsupported-schema` entry.

## Scenario 5 — the git-tracking opt-out (Q1/FR-020)

1. In a fresh scratch repo with Continuity generating `.continuity/`
   content, run whatever documented command `docs/install.md` provides for
   the opt-out (adding `.continuity/` to `.gitignore`, and — if any content
   is already tracked — a one-time `git rm -r --cached .continuity/`).
2. **Expected**: `git status` no longer shows `.continuity/` as trackable;
   Continuity continues to read/write it exactly as before (the opt-out is
   purely a version-control decision, not a functional one).
