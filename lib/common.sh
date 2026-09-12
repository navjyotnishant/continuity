#!/usr/bin/env bash
# lib/common.sh — shared path resolution, failure logging, and metadata
# defaults used by every other Continuity script.
#
# Targets bash 3.2 (macOS stock) and bash >= 4 (Linux) — no bashisms newer
# than that (associative arrays, `${var,,}`, `mapfile`, `local -n`).
#
# Every function is scoped by an explicit directory argument (a project
# `cwd` or a `.continuity` dir) rather than a global/env var, because every
# hook in contracts/hook-io-contract.md receives its project `cwd` on stdin
# per-invocation — there is no ambient "current project" to assume.

# continuity_dir <cwd>
# Prints the `.continuity/` path for a given project `cwd`. Pure string
# resolution — does not check existence or create anything.
continuity_dir() {
  local cwd="$1"
  cwd="${cwd%/}"
  printf '%s/.continuity\n' "$cwd"
}

# continuity_log <continuity-dir> <operation> <failure-kind> <detail>
# Appends one scrubbed, pipe-delimited line to <continuity-dir>/errors.log
# per contracts/file-format-contract.md:
#   <ISO-8601 UTC timestamp> | <operation> | <failure-kind> | <detail>
# Fail-open (FR-012): creates <continuity-dir> if missing; if the append
# itself fails for any reason (no permission, disk full, missing parent),
# this silently no-ops rather than raising an error of its own.
continuity_log() {
  local dir="$1" operation="$2" kind="$3" detail="$4"
  local ts scrub_op scrub_kind scrub_detail

  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || return 0

  # Scrub `|` and newlines out of each field so the line stays parseable as
  # the contract's fixed four-field shape — this is line-shape hygiene, not
  # the secret-scanning gate (that is lib/secret_scan.sh's job elsewhere).
  scrub_op="$(printf '%s' "$operation" | tr '|\n' '  ')"
  scrub_kind="$(printf '%s' "$kind" | tr '|\n' '  ')"
  scrub_detail="$(printf '%s' "$detail" | tr '|\n' '  ')"

  mkdir -p "$dir" 2>/dev/null || return 0
  printf '%s | %s | %s | %s\n' "$ts" "$scrub_op" "$scrub_kind" "$scrub_detail" \
    >> "$dir/errors.log" 2>/dev/null || return 0
}

# continuity_metadata_read <continuity-dir>
# Reads `retention_days` and `git_tracked` out of <continuity-dir>/metadata.json,
# setting the globals CONTINUITY_RETENTION_DAYS and CONTINUITY_GIT_TRACKED.
# Defaults to 60 / true (data-model.md's stated defaults) when the file is
# absent, unreadable, or the field can't be found — never fails, never
# writes anything (reading defaults is not the same operation as
# lib/migrate.sh's metadata_ensure, which creates the file).
continuity_metadata_read() {
  local dir="$1" file value

  CONTINUITY_RETENTION_DAYS=60
  CONTINUITY_GIT_TRACKED=true

  file="$dir/metadata.json"
  [ -r "$file" ] || return 0

  value="$(grep -oE '"retention_days"[[:space:]]*:[[:space:]]*[0-9]+' "$file" 2>/dev/null \
    | head -n1 | grep -oE '[0-9]+$')"
  [ -n "$value" ] && CONTINUITY_RETENTION_DAYS="$value"

  value="$(grep -oE '"git_tracked"[[:space:]]*:[[:space:]]*(true|false)' "$file" 2>/dev/null \
    | head -n1 | grep -oE 'true|false')"
  [ -n "$value" ] && CONTINUITY_GIT_TRACKED="$value"

  return 0
}
