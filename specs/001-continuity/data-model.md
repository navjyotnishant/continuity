# Phase 1 Data Model: Continuity

Every entity below is from the spec's Key Entities section. Each maps to a
concrete file and on-disk shape under `.continuity/` (created at runtime in
an installed project — see plan.md → Project Structure).

## Storage overview

| Entity (spec) | File | Retention |
|---|---|---|
| State Note | `.continuity/state.md` | Superseded in place — one current state per project, not accumulated (durable, indefinite) |
| Constraint | `.continuity/state.md` (`## Constraints` section) | Indefinite |
| Decision Record | `.continuity/decisions.md` | Indefinite (append-only) |
| Task Entry | `.continuity/tasks.md` | Indefinite; status transitions in place |
| Learning | `.continuity/learnings.md` | Indefinite (append-only) |
| (Established convention — not a separate spec entity, but named in FR-002) | `.continuity/learnings.md` (`## Conventions` section) | Indefinite |
| Session Handoff | `.continuity/sessions/<UTC-timestamp>-<pid>.md` | Configurable, default 60 days (Q6) |
| Failure Log Entry | `.continuity/errors.log` | Configurable, default 60 days (Q8) |
| (schema/versioning — infrastructure, not a spec entity) | `.continuity/metadata.json` | Indefinite (one current version) |

Constraints get no dedicated file: Q6 names exactly four durable files
(`state.md`, `decisions.md`, `tasks.md`, `learnings.md`), and constraints are
few, slow-changing, and closely tied to current state, so they fold into
`state.md` rather than becoming a fifth file the spec's own answered question
did not name.

## Entity: State Note

**File**: `.continuity/state.md` (single file, rewritten in place — this is
the one durable file that is *replaced*, not appended to, per the spec's "
Superseded by newer state notes rather than accumulated indefinitely").

**Fields**:
- `updated_at` (ISO-8601 UTC timestamp) — when this state was last written.
- `summary` (free text, target 5–15 lines) — what exists, what's in progress.
- `## Constraints` (bulleted list) — known limitations/hard requirements,
  sourced from the intent doc or discovered during work.

**Validation rules**:
- `updated_at` MUST be present and parseable; `select_context.py` treats a
  file missing or failing this check as corrupted and skips it (FR-013),
  logging to `errors.log`.
- A write MUST NOT reduce `state.md` to an empty file — `write_memory.py`
  writes the new version to a temp path and only renames over the original
  if the new content is non-empty (guards against a trigger that produces no
  meaningful summary silently wiping prior state).

## Entity: Decision Record

**File**: `.continuity/decisions.md` (append-only; one Markdown section per
entry).

**Fields** (per entry):
- `## Decision: <short title>`
- `captured_at` (ISO-8601 UTC timestamp)
- `category: decision` (provenance tag, FR-004)
- Body: what was decided and why, enough to not be re-litigated (per the
  spec's Key Entities description).

**Validation rules**:
- Each entry MUST carry `captured_at` and `category` — an entry missing
  either is treated as malformed and excluded from the bounded
  `SessionStart` subset (isolated per-entry, not per-file, since
  `decisions.md` is append-only and one bad entry should not hide the
  others).
- `secret_scan.py` runs over the entry body before it is appended (R5);
  a match drops that line, not the whole entry, and logs the drop.

## Entity: Task Entry

**File**: `.continuity/tasks.md` (append/update; status is mutated in place
for an existing entry rather than appended as a new one).

**Fields** (per entry):
- `## Task: <short title>`
- `status`: one of `active`, `blocked`, `done`.
- `captured_at` / `updated_at` (ISO-8601 UTC timestamps).
- `category: task`
- Body: what the task is, and (if `blocked`) what it is blocked on.

**Validation rules**:
- `status` MUST be one of the three enumerated values; an unrecognized value
  is treated as malformed and the entry is excluded from `SessionStart`
  loading (fail open at the entry level).
- `select_context.py` prioritizes `active` and `blocked` entries over `done`
  ones when bounding to the line-budget target (most-recent-first within
  each status), since active/unfinished work is what User Story 1's
  Independent Test checks for first.

## Entity: Learning

**File**: `.continuity/learnings.md` (append-only; a `## Conventions`
section holds established-convention entries distinctly from `##
Learnings`).

**Fields** (per entry):
- `## Learning: <short title>` or `## Convention: <short title>`
- `captured_at` (ISO-8601 UTC timestamp)
- `category: learning` or `category: convention`
- Body: the discovery or convention, worth not re-discovering.

**Validation rules**: Same shape and same per-entry fail-open handling as
Decision Record.

## Entity: Session Handoff

**File**: One file per checkpoint under `.continuity/sessions/`, named
`<UTC-timestamp>-<pid>.md` (the PID disambiguates two concurrent sessions
checkpointing in the same second).

**Fields**:
- `captured_at` (ISO-8601 UTC timestamp, also encoded in the filename).
- `trigger`: one of `file-change`, `git-diff`, `task-event`,
  `decision-event`, `test-milestone`, `explicit-checkpoint`, `session-end` —
  which meaningful-change signal produced this handoff (traceability for
  debugging the trigger logic itself).
- Body: a short note (target under 20 lines) summarizing what a following
  session needs to know to continue — the spec's "not only `SessionEnd`"
  requirement (FR-009) means this file type is written by every trigger kind,
  not just `SessionEnd`.

**Validation rules**:
- Governed by `lib/retention.py`: any file under `sessions/` older than the
  configured retention window (default 60 days, `metadata.json` →
  `retention_days`) is deleted. Information promoted into a durable file
  (state/decisions/tasks/learnings) before pruning is unaffected by that
  file's later deletion — promotion, not the handoff file itself, is what
  makes a fact durable (per Q6's "important information promoted into
  durable context should not be removed during session-history pruning").

## Entity: Failure Log Entry

**File**: `.continuity/errors.log` (append-only, one line per entry, plain
text — deliberately not Markdown, since this is an operational log rather
than injected context).

**Fields** (per line, pipe-delimited):
`<ISO-8601 UTC timestamp> | <operation> | <failure-kind> | <detail>`

- `operation`: e.g. `session-start-load`, `write-decisions`, `lock-acquire`,
  `secret-scan-block`, `migrate`.
- `failure-kind`: one of `missing`, `unreadable`, `corrupted`,
  `write-failed`, `timeout`, `lock-unavailable`, `secret-blocked`,
  `unsupported-schema`.
- `detail`: a short, scrubbed description — **never** raw file content,
  conversation content, secrets, or credentials (per Q8's answer). For a
  `secret-blocked` entry, `detail` names only the matched pattern category
  (e.g. `aws-key-pattern`), never the matched text.

**Validation rules**:
- Governed by the same `retention.py` window as `sessions/` (default 60
  days per Q8) — old lines are trimmed from the head of the file.
- A failure to write to `errors.log` itself is the one failure Continuity
  does not attempt to log (would recurse); it is silently swallowed, per
  FR-012's "skip the operation" — logging the failure to log is not itself
  a requirement the spec makes.

## Infrastructure: `metadata.json`

Not a spec entity, but the versioning/config backbone every other file's
compatibility handling depends on (Q9).

**Fields**:
```json
{
  "schema_version": "1.0",
  "plugin_version": "<semver of the installed plugin>",
  "created_at": "<ISO-8601 UTC timestamp>",
  "retention_days": 60,
  "git_tracked": true
}
```

**Validation rules**:
- `schema_version` compatibility: a plugin supports its own current schema
  version and exactly one previous version. Reading a file at the previous
  version triggers `lib/migrate.py` to rewrite it forward (atomically, via
  `atomic_write.py`) before use. Reading a file at an unsupported *newer*
  version (a teammate on a newer plugin wrote it) causes the current
  operation to fail open — skip, log `unsupported-schema`, do not modify the
  file — exactly per Q9's answer.
- `retention_days` and `git_tracked` are user-configurable (a developer may
  hand-edit `metadata.json`); `write_memory.py` and `retention.py` read this
  file fresh on every run rather than caching it, since a hand-edit mid-
  session (an explicit spec edge case) must take effect without a restart.

## State transitions

- **State Note**: no discrete states — each write fully replaces the prior
  content (see Validation rules above).
- **Task Entry**: `active` → `blocked` → `active` (unblocked) → `done`.
  `done` is terminal; a task is never deleted, only marked `done`, so it
  remains available as project history and is simply deprioritized by
  `select_context.py`'s bounding logic.
- **`.continuity/` store as a whole**: `absent` → `present, schema-current`
  → (on a plugin upgrade) `present, schema-outdated` → (on next read/write)
  `present, schema-current` (migrated) or `present, schema-unsupported`
  (newer than this plugin understands — permanently skipped until the
  plugin itself is upgraded).
