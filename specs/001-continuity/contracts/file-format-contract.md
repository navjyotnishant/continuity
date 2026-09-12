# Contract: `.continuity/` File Formats

This is the contract every version of the plugin must honor when reading or
writing `.continuity/` content, so an older plugin reading a newer project's
files (or vice versa) has defined, not undefined, behavior (Q9).

## `metadata.json`

- MUST be valid JSON with at least `schema_version` (string, e.g. `"1.0"`)
  and `plugin_version` (string, semver).
- A reader supports exactly its own `schema_version` and the one immediately
  prior. On an older-but-supported version, the reader migrates the *entire*
  `.continuity/` store forward (rewriting any file whose format changed
  between versions) atomically before proceeding, then rewrites
  `metadata.json` with the new `schema_version`.
- On an unsupported newer `schema_version` (major version ahead of what this
  plugin understands), the reader performs **no write of any kind** anywhere
  in `.continuity/`, logs `unsupported-schema` to `errors.log`, and treats
  the store as if it were absent for this operation (fail open).
- Absent `metadata.json` with other `.continuity/` files present is treated
  as `schema_version: "1.0"` (the version that predates `metadata.json`'s
  own introduction) for backward compatibility with a store created by a
  hypothetical pre-metadata build — not expected in practice since this is
  the first shipped version, but the rule is stated for future-proofing.

## Durable Markdown files (`state.md`, `decisions.md`, `tasks.md`,
`learnings.md`)

- Encoding: UTF-8, LF line endings, trailing newline required.
- Every entry (in `decisions.md`, `tasks.md`, `learnings.md`) is a `##`-
  level Markdown heading followed by a fenced metadata line and a free-text
  body, per data-model.md's per-entity field lists. A parser MUST treat a
  `##` heading as the start of a new entry and MUST NOT require any
  particular heading text beyond the `## <Kind>: <title>` shape — titles are
  free text.
- A required field (`captured_at`, `category`, and for tasks, `status`)
  missing from an entry invalidates *that entry only*; a parser MUST
  continue past it to the next `##` heading rather than aborting the whole
  file (FR-013's "isolated to itself," applied at entry granularity for
  append-only files).
- `state.md` has no entry structure — it is a single current snapshot, so
  "invalid" for `state.md` means "missing or unparseable `updated_at`,"
  which invalidates the whole file (there is only one entry to invalidate).

## `errors.log`

- Encoding: UTF-8, LF line endings, one entry per line, pipe-delimited (see
  data-model.md's Failure Log Entry fields). A line that does not match the
  four-field shape is skipped by any reader/pruner rather than treated as a
  fatal parse error (the log itself must never be a source of a blocking
  failure).

## Session handoff files (`sessions/<timestamp>-<pid>.md`)

- Filename format: `<UTC-timestamp, ISO-8601 basic format, colons/periods
  stripped for filesystem safety>-<pid>.md`, e.g.
  `20260912T140501Z-48213.md`. This format is depended on by
  `lib/retention.py` (parses the timestamp from the filename to decide
  pruning eligibility without opening the file) and by `select_context.py`
  (sorts by filename to find the most recent handoff without a directory
  listing's mtime, which can be unreliable across some filesystems/clones).
- Body format: `captured_at` and `trigger` as a fenced metadata line,
  followed by free text, per data-model.md.

## Atomicity (applies to every write above)

- Every write goes through `lib/atomic_write.py`: content is written via
  `tempfile.NamedTemporaryFile` to a temp file in the same directory as
  `<target>` (prefix `<target's basename>.tmp.` so the file is recognizable
  as crash debris), then `os.replace()`'d onto `<target>`. `os.replace()` is
  atomic on both POSIX and native Windows when source and destination are on
  the same filesystem, so a reader never observes a partially-written file
  (FR-014) on any of the three target platforms (Q11). A crash between the
  write and the `os.replace()` leaves only an orphaned `<target's
  basename>.tmp.*` file, which `lib/retention.py` also sweeps (any such file
  older than an hour is removed as crash debris).

## Compatibility guarantee this contract provides

Given the rules above, an older plugin encountering a store written by a
newer, schema-compatible plugin version can always read it (unknown extra
fields in a metadata line are ignored, not rejected); an older plugin
encountering a store at an unsupported newer *schema* version always fails
open without corrupting it; and a newer plugin encountering an older,
supported schema version always migrates it forward before use rather than
operating on two different formats side by side.
