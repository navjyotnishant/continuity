#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Unit tests for lib/migrate.sh's metadata.json schema-version
#              compatibility rules (T012).

set -u

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Schema versions exercised by these tests.
#   SCHEMA_CURRENT must match templates/metadata.json.tmpl (T008).
#   SCHEMA_PREV must match the one-version-back release that
#     lib/migrate.sh (T007) accepts and migrates forward.
#   SCHEMA_NEWER is a major version ahead of anything this plugin understands.
SCHEMA_CURRENT="1.0"
SCHEMA_PREV="0.9"
SCHEMA_NEWER="2.0"
# Older than SCHEMA_PREV: not "exactly its own or the one immediately prior"
# per file-format-contract.md, so it is unsupported the same way a too-new
# version is.
SCHEMA_TOO_OLD="0.1"
# Between SCHEMA_PREV and SCHEMA_CURRENT: matches neither exactly, so per the
# same contract sentence it is unsupported too, not a partial match.
SCHEMA_INTERMEDIATE="0.95"

FAILURES=0

assert_eq() { # expected actual msg
  if [ "$1" = "$2" ]; then
    printf 'ok   - %s\n' "$3"
  else
    printf 'FAIL - %s\n       expected: [%s]\n       actual:   [%s]\n' "$3" "$1" "$2"
    FAILURES=$((FAILURES + 1))
  fi
}

assert_ok() { # rc msg
  assert_eq "0" "$1" "$2"
}

assert_nonzero() { # rc msg
  if [ "$1" -ne 0 ]; then
    printf 'ok   - %s\n' "$2"
  else
    printf 'FAIL - %s\n       expected non-zero exit, got: [%s]\n' "$2" "$1"
    FAILURES=$((FAILURES + 1))
  fi
}

# Read a top-level string field out of a JSON file without a JSON parser
# (plan.md: standard POSIX tools only, no Python/Node runtime dependency).
json_string() { # file key
  sed -n "s/.*\"$2\"[[:space:]]*:[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$1" | head -n 1
}

# Build a .continuity/ store at a given schema_version and echo its path.
make_store() { # schema_version
  local dir
  dir="$(mktemp -d "${TMPDIR:-/tmp}/continuity-migrate-test.XXXXXX")/.continuity"
  mkdir -p "$dir"
  cat >"$dir/metadata.json" <<EOF
{
  "schema_version": "$1",
  "plugin_version": "0.1.0",
  "created_at": "2026-09-12T00:00:00Z",
  "retention_days": 60,
  "git_tracked": true
}
EOF
  printf '# Project State\n\nupdated_at: 2026-09-12T00:00:00Z\n\n## Constraints\n\n' \
    >"$dir/state.md"
  printf '%s' "$dir"
}

# Build a .continuity/ store whose metadata.json is given verbatim (used for
# shapes make_store cannot produce: a missing or malformed schema_version).
make_store_raw() { # metadata.json-content
  local dir
  dir="$(mktemp -d "${TMPDIR:-/tmp}/continuity-migrate-test.XXXXXX")/.continuity"
  mkdir -p "$dir"
  printf '%s' "$1" >"$dir/metadata.json"
  printf '# Project State\n\nupdated_at: 2026-09-12T00:00:00Z\n\n## Constraints\n\n' \
    >"$dir/state.md"
  printf '%s' "$dir"
}

if [ ! -f "$REPO_ROOT/lib/migrate.sh" ]; then
  printf 'FAIL - lib/migrate.sh not found (T007 has not landed yet)\n' >&2
  exit 1
fi
# shellcheck source=/dev/null
. "$REPO_ROOT/lib/migrate.sh"

# --- A file at the current schema version is left untouched -----------------
store="$(make_store "$SCHEMA_CURRENT")"
before="$(cat "$store/metadata.json")"
before_state="$(cat "$store/state.md")"
metadata_check_and_migrate "$store"
rc=$?
assert_ok "$rc" "current schema version is supported"
assert_eq "$before" "$(cat "$store/metadata.json")" \
  "metadata.json at the current schema version is byte-for-byte unchanged"
assert_eq "$before_state" "$(cat "$store/state.md")" \
  "state.md is not rewritten when the schema version is already current"
if [ -f "$store/errors.log" ]; then
  printf 'FAIL - errors.log is not created for a no-op current-schema call\n'
  FAILURES=$((FAILURES + 1))
else
  printf 'ok   - errors.log is not created for a no-op current-schema call\n'
fi
rm -rf "$(dirname "$store")"

# --- A file at the previous schema version is migrated forward --------------
store="$(make_store "$SCHEMA_PREV")"
before_state="$(cat "$store/state.md")"
metadata_check_and_migrate "$store"
rc=$?
assert_ok "$rc" "previous schema version is supported"
assert_eq "$SCHEMA_CURRENT" "$(json_string "$store/metadata.json" schema_version)" \
  "metadata.json at the previous schema version gains the current schema_version"
assert_eq "$before_state" "$(cat "$store/state.md")" \
  "state.md is not rewritten when migrating metadata.json forward"
if [ -f "$store/errors.log" ]; then
  printf 'FAIL - errors.log is not created for a successful migration\n'
  FAILURES=$((FAILURES + 1))
else
  printf 'ok   - errors.log is not created for a successful migration\n'
fi
rm -rf "$(dirname "$store")"

# --- A file at an unsupported newer version is never written to -------------
# Per file-format-contract.md: no write of any kind in .continuity/, an
# unsupported-schema line in errors.log, and the store is treated as absent
# for this operation (fail open).
store="$(make_store "$SCHEMA_NEWER")"
before_metadata="$(cat "$store/metadata.json")"
before_state="$(cat "$store/state.md")"
metadata_check_and_migrate "$store"
rc=$?
assert_eq "$before_metadata" "$(cat "$store/metadata.json")" \
  "metadata.json at an unsupported newer version is byte-for-byte unchanged"
assert_eq "$before_state" "$(cat "$store/state.md")" \
  "state.md is not rewritten when the schema version is unsupported"
if [ -f "$store/errors.log" ] && grep -q 'unsupported-schema' "$store/errors.log"; then
  printf 'ok   - errors.log gains an unsupported-schema line\n'
else
  printf 'FAIL - errors.log gains an unsupported-schema line\n'
  FAILURES=$((FAILURES + 1))
fi
# Fail-open per file-format-contract.md: the store is treated as absent for
# this operation, which the caller can only detect via a non-zero return —
# a 0 here would make an unsupported store indistinguishable from a
# supported one to every caller of metadata_check_and_migrate.
assert_nonzero "$rc" \
  "metadata_check_and_migrate returns non-zero for an unsupported newer schema version"
rm -rf "$(dirname "$store")"

# --- A metadata.json with no schema_version field is handled without a crash
# or a corrupting write. file-format-contract.md requires schema_version to
# be present; a store missing it can't be compared against SCHEMA_CURRENT/
# SCHEMA_PREV, so it gets the same fail-open treatment as an unsupported
# version: no write anywhere in .continuity/ and an error logged.
store="$(make_store_raw '{
  "plugin_version": "0.1.0",
  "created_at": "2026-09-12T00:00:00Z",
  "retention_days": 60,
  "git_tracked": true
}')"
before_metadata="$(cat "$store/metadata.json")"
before_state="$(cat "$store/state.md")"
metadata_check_and_migrate "$store"
rc=$?
assert_nonzero "$rc" \
  "metadata_check_and_migrate returns non-zero when schema_version is missing"
assert_eq "$before_metadata" "$(cat "$store/metadata.json")" \
  "metadata.json with no schema_version field is byte-for-byte unchanged"
assert_eq "$before_state" "$(cat "$store/state.md")" \
  "state.md is not rewritten when schema_version is missing"
if [ -f "$store/errors.log" ] && [ -s "$store/errors.log" ]; then
  printf 'ok   - errors.log gains a line when schema_version is missing\n'
else
  printf 'FAIL - errors.log gains a line when schema_version is missing\n'
  FAILURES=$((FAILURES + 1))
fi
rm -rf "$(dirname "$store")"

# --- A schema_version that is not a valid version string is handled without
# a crash or a corrupting write, for the same reason: it can't be compared
# against SCHEMA_CURRENT/SCHEMA_PREV, so it fails open like an unsupported
# version rather than being silently accepted or crashing the caller.
store="$(make_store 'not-a-version')"
before_metadata="$(cat "$store/metadata.json")"
before_state="$(cat "$store/state.md")"
metadata_check_and_migrate "$store"
rc=$?
assert_nonzero "$rc" \
  "metadata_check_and_migrate returns non-zero for a malformed schema_version"
assert_eq "$before_metadata" "$(cat "$store/metadata.json")" \
  "metadata.json with a malformed schema_version is byte-for-byte unchanged"
assert_eq "$before_state" "$(cat "$store/state.md")" \
  "state.md is not rewritten when schema_version is malformed"
if [ -f "$store/errors.log" ] && [ -s "$store/errors.log" ]; then
  printf 'ok   - errors.log gains a line when schema_version is malformed\n'
else
  printf 'FAIL - errors.log gains a line when schema_version is malformed\n'
  FAILURES=$((FAILURES + 1))
fi
rm -rf "$(dirname "$store")"

# --- All fields other than schema_version survive a migration untouched -----
store="$(make_store "$SCHEMA_PREV")"
metadata_check_and_migrate "$store"
assert_eq "0.1.0" "$(json_string "$store/metadata.json" plugin_version)" \
  "plugin_version is preserved across a schema_version migration"
assert_eq "2026-09-12T00:00:00Z" "$(json_string "$store/metadata.json" created_at)" \
  "created_at is preserved across a schema_version migration"
assert_eq "60" "$(sed -n 's/.*"retention_days"[[:space:]]*:[[:space:]]*\([0-9]*\).*/\1/p' \
  "$store/metadata.json" | head -n 1)" \
  "retention_days is preserved across a schema_version migration"
assert_eq "true" "$(sed -n 's/.*"git_tracked"[[:space:]]*:[[:space:]]*\(true\|false\).*/\1/p' \
  "$store/metadata.json" | head -n 1)" \
  "git_tracked is preserved across a schema_version migration"
rm -rf "$(dirname "$store")"

# --- A schema version older than SCHEMA_PREV is unsupported, same as newer --
# file-format-contract.md supports "exactly its own schema_version and the
# one immediately prior" -- SCHEMA_TOO_OLD is neither, so it gets the same
# fail-open treatment as an unsupported newer version: no write anywhere in
# .continuity/, an unsupported-schema line in errors.log, non-zero return.
store="$(make_store "$SCHEMA_TOO_OLD")"
before_metadata="$(cat "$store/metadata.json")"
before_state="$(cat "$store/state.md")"
metadata_check_and_migrate "$store"
rc=$?
assert_nonzero "$rc" \
  "metadata_check_and_migrate returns non-zero for a schema version older than SCHEMA_PREV"
assert_eq "$before_metadata" "$(cat "$store/metadata.json")" \
  "metadata.json older than SCHEMA_PREV is byte-for-byte unchanged"
assert_eq "$before_state" "$(cat "$store/state.md")" \
  "state.md is not rewritten when the schema version is older than SCHEMA_PREV"
if [ -f "$store/errors.log" ] && grep -q 'unsupported-schema' "$store/errors.log"; then
  printf 'ok   - errors.log gains an unsupported-schema line for a too-old version\n'
else
  printf 'FAIL - errors.log gains an unsupported-schema line for a too-old version\n'
  FAILURES=$((FAILURES + 1))
fi
rm -rf "$(dirname "$store")"

# --- A schema version strictly between SCHEMA_PREV and SCHEMA_CURRENT is also
# unsupported: it matches neither exactly, so the same contract sentence
# denies it the migrate-forward path reserved for an exact SCHEMA_PREV match.
store="$(make_store "$SCHEMA_INTERMEDIATE")"
before_metadata="$(cat "$store/metadata.json")"
before_state="$(cat "$store/state.md")"
metadata_check_and_migrate "$store"
rc=$?
assert_nonzero "$rc" \
  "metadata_check_and_migrate returns non-zero for a schema version between SCHEMA_PREV and SCHEMA_CURRENT"
assert_eq "$before_metadata" "$(cat "$store/metadata.json")" \
  "metadata.json at an intermediate schema version is byte-for-byte unchanged"
assert_eq "$before_state" "$(cat "$store/state.md")" \
  "state.md is not rewritten when the schema version is intermediate"
if [ -f "$store/errors.log" ] && grep -q 'unsupported-schema' "$store/errors.log"; then
  printf 'ok   - errors.log gains an unsupported-schema line for an intermediate version\n'
else
  printf 'FAIL - errors.log gains an unsupported-schema line for an intermediate version\n'
  FAILURES=$((FAILURES + 1))
fi
rm -rf "$(dirname "$store")"

# --- A .continuity directory that does not exist is handled without a crash
# T012: the store may be created, the call may fail, or it may be treated as
# absent — file-format-contract.md does not mandate one specific behavior
# here, only that nothing crashes and the caller can tell what happened
# (either the store now exists, or the return code says it did not succeed).
parent="$(mktemp -d "${TMPDIR:-/tmp}/continuity-migrate-test.XXXXXX")"
store="$parent/.continuity"
metadata_check_and_migrate "$store"
rc=$?
if [ -d "$store" ] || [ "$rc" -ne 0 ]; then
  printf 'ok   - missing .continuity directory is created or reported as a non-zero failure\n'
else
  printf 'FAIL - missing .continuity directory was silently treated as success with nothing created\n'
  FAILURES=$((FAILURES + 1))
fi
rm -rf "$parent"

# --- A .continuity directory with no metadata.json is handled without a
# crash or a corrupting write. file-format-contract.md treats an absent
# metadata.json (with other .continuity/ files present) as schema_version
# "1.0" for backward compatibility, but T012 only requires that the store
# come out either with a metadata.json created, or reported as failed/absent
# — not one single mandated shape.
parent="$(mktemp -d "${TMPDIR:-/tmp}/continuity-migrate-test.XXXXXX")"
store="$parent/.continuity"
mkdir -p "$store"
printf '# Project State\n\nupdated_at: 2026-09-12T00:00:00Z\n\n## Constraints\n\n' \
  >"$store/state.md"
before_state="$(cat "$store/state.md")"
metadata_check_and_migrate "$store"
rc=$?
if [ -f "$store/metadata.json" ] || [ "$rc" -ne 0 ]; then
  printf 'ok   - missing metadata.json is created or reported as a non-zero failure\n'
else
  printf 'FAIL - missing metadata.json was silently treated as success with nothing created\n'
  FAILURES=$((FAILURES + 1))
fi
if [ ! -f "$store/metadata.json" ]; then
  assert_eq "$before_state" "$(cat "$store/state.md")" \
    "state.md is not rewritten when metadata.json is missing and none is created"
fi
rm -rf "$parent"

# --- Corrupted (invalid-JSON) metadata.json is detected and logged, never --
# silently accepted or written over -------------------------------------
store="$(make_store_raw '{ "schema_version": "1.0", not valid json !!! ')"
before_metadata="$(cat "$store/metadata.json")"
before_state="$(cat "$store/state.md")"
metadata_check_and_migrate "$store"
rc=$?
assert_nonzero "$rc" \
  "metadata_check_and_migrate returns non-zero for invalid-JSON metadata.json"
assert_eq "$before_metadata" "$(cat "$store/metadata.json")" \
  "invalid-JSON metadata.json is byte-for-byte unchanged"
assert_eq "$before_state" "$(cat "$store/state.md")" \
  "state.md is not rewritten when metadata.json is invalid JSON"
if [ -f "$store/errors.log" ] && [ -s "$store/errors.log" ]; then
  printf 'ok   - errors.log gains a line when metadata.json is invalid JSON\n'
else
  printf 'FAIL - errors.log gains a line when metadata.json is invalid JSON\n'
  FAILURES=$((FAILURES + 1))
fi
rm -rf "$(dirname "$store")"

CONCURRENCY=5

# --- Concurrent calls: a successful migration converges cleanly -------------
# Simulates two-or-more sessions racing a migration the way plan.md's
# test_lock.sh simulates lock contention: several backgrounded subshells
# hitting the same store at once. metadata_check_and_migrate must own enough
# synchronization internally that the result is indistinguishable from a
# single call, not a merged or half-written file.
store="$(make_store "$SCHEMA_PREV")"
for _ in $(seq 1 "$CONCURRENCY"); do
  ( metadata_check_and_migrate "$store" ) &
done
wait
assert_eq "$SCHEMA_CURRENT" "$(json_string "$store/metadata.json" schema_version)" \
  "concurrent migrations from the previous schema version converge on the current one"
assert_eq "1" "$(grep -c '"schema_version"' "$store/metadata.json")" \
  "metadata.json has exactly one schema_version field after concurrent migrations (not a torn/merged file)"
assert_eq "1" "$(grep -c '"plugin_version"' "$store/metadata.json")" \
  "metadata.json has exactly one plugin_version field after concurrent migrations (not a torn/merged file)"
if [ ! -s "$store/errors.log" ] 2>/dev/null || [ ! -e "$store/errors.log" ]; then
  printf 'ok   - concurrent successful migrations do not write to errors.log\n'
else
  printf 'FAIL - concurrent successful migrations do not write to errors.log\n'
  FAILURES=$((FAILURES + 1))
fi
rm -rf "$(dirname "$store")"

# --- Concurrent calls: an unsupported version never corrupts or double-logs -
# Same race, but against a store none of the callers can migrate. Every
# caller fails open, so the files on disk must be exactly what they were
# before, and errors.log may gain one line per caller but never a torn or
# merged line -- that is what an unsynchronized append to the same file
# would produce, not a "duplicate" in the sense of a repeated but
# well-formed entry.
store="$(make_store "$SCHEMA_NEWER")"
before_metadata="$(cat "$store/metadata.json")"
before_state="$(cat "$store/state.md")"
for _ in $(seq 1 "$CONCURRENCY"); do
  ( metadata_check_and_migrate "$store" ) &
done
wait
assert_eq "$before_metadata" "$(cat "$store/metadata.json")" \
  "metadata.json is unchanged after concurrent calls on an unsupported schema version"
assert_eq "$before_state" "$(cat "$store/state.md")" \
  "state.md is unchanged after concurrent calls on an unsupported schema version"
if [ -f "$store/errors.log" ]; then
  malformed="$(grep -vc '^[^|]*|[^|]*|unsupported-schema|[^|]*$' "$store/errors.log")"
  assert_eq "0" "$malformed" \
    "every concurrent unsupported-schema line in errors.log is a complete, well-formed entry"
else
  printf 'FAIL - errors.log gains an unsupported-schema line after concurrent calls\n'
  FAILURES=$((FAILURES + 1))
fi
rm -rf "$(dirname "$store")"

# --- Permission denied -------------------------------------------------------
# A read-only or write-protected store directory must fail closed: a
# non-zero return, and every file already on disk left exactly as found --
# no partial metadata.json, no orphaned atomic_write.sh .tmp.<pid> file.
if [ "$(id -u)" -eq 0 ]; then
  printf 'ok   - skipping permission-denied case (running as root; chmod is not enforced)\n'
else
  store="$(make_store "$SCHEMA_PREV")"
  before_metadata="$(cat "$store/metadata.json")"
  before_state="$(cat "$store/state.md")"
  chmod 555 "$store"
  metadata_check_and_migrate "$store"
  rc=$?
  chmod 755 "$store"
  assert_nonzero "$rc" \
    "metadata_check_and_migrate fails when the store directory is write-protected"
  assert_eq "$before_metadata" "$(cat "$store/metadata.json")" \
    "metadata.json is unchanged when a migration cannot write to a read-only store"
  assert_eq "$before_state" "$(cat "$store/state.md")" \
    "state.md is unchanged when a migration cannot write to a read-only store"
  if ls "$store"/*.tmp.* >/dev/null 2>&1; then
    printf 'FAIL - no orphaned .tmp.<pid> file after a write-protected migration attempt\n'
    FAILURES=$((FAILURES + 1))
  else
    printf 'ok   - no orphaned .tmp.<pid> file after a write-protected migration attempt\n'
  fi
  rm -rf "$(dirname "$store")"
fi

# --- errors.log already exists -----------------------------------------------
# Appending to an existing errors.log must never truncate or reorder its
# prior entries -- only add to them (retention.sh, not migrate.sh, is what
# ever trims the head of this file).
store="$(make_store "$SCHEMA_NEWER")"
prior_line='2026-09-01T00:00:00Z|session-start-load|missing|state.md'
printf '%s\n' "$prior_line" >"$store/errors.log"
metadata_check_and_migrate "$store"
rc=$?
assert_nonzero "$rc" \
  "metadata_check_and_migrate still returns non-zero when errors.log already exists"
assert_eq "$prior_line" "$(sed -n '1p' "$store/errors.log")" \
  "the pre-existing errors.log entry survives unchanged as the first line"
if grep -q 'unsupported-schema' "$store/errors.log"; then
  printf 'ok   - a new unsupported-schema line is appended after the prior entry\n'
else
  printf 'FAIL - a new unsupported-schema line is appended after the prior entry\n'
  FAILURES=$((FAILURES + 1))
fi
assert_eq "2" "$(wc -l <"$store/errors.log" | tr -d ' ')" \
  "errors.log has exactly the prior entry plus one new entry -- no truncation, no duplication"
rm -rf "$(dirname "$store")"

if [ "$FAILURES" -ne 0 ]; then
  printf '\n%s assertion(s) failed in %s\n' "$FAILURES" "$(basename "${BASH_SOURCE[0]}")" >&2
  exit 1
fi
printf '\nall assertions passed in %s\n' "$(basename "${BASH_SOURCE[0]}")"
