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

if [ ! -f "$REPO_ROOT/lib/migrate.sh" ]; then
  printf 'FAIL - lib/migrate.sh not found (T007 has not landed yet)\n' >&2
  exit 1
fi
# shellcheck source=/dev/null
. "$REPO_ROOT/lib/migrate.sh"

# --- A file at the current schema version is left untouched -----------------
store="$(make_store "$SCHEMA_CURRENT")"
before="$(cat "$store/metadata.json")"
metadata_check_and_migrate "$store"
rc=$?
assert_ok "$rc" "current schema version is supported"
assert_eq "$before" "$(cat "$store/metadata.json")" \
  "metadata.json at the current schema version is byte-for-byte unchanged"
rm -rf "$(dirname "$store")"

# --- A file at the previous schema version is migrated forward --------------
store="$(make_store "$SCHEMA_PREV")"
metadata_check_and_migrate "$store"
rc=$?
assert_ok "$rc" "previous schema version is supported"
assert_eq "$SCHEMA_CURRENT" "$(json_string "$store/metadata.json" schema_version)" \
  "metadata.json at the previous schema version gains the current schema_version"
rm -rf "$(dirname "$store")"

# --- A file at an unsupported newer version is never written to -------------
# Per file-format-contract.md: no write of any kind in .continuity/, an
# unsupported-schema line in errors.log, and the store is treated as absent
# for this operation (fail open).
store="$(make_store "$SCHEMA_NEWER")"
before_metadata="$(cat "$store/metadata.json")"
before_state="$(cat "$store/state.md")"
metadata_check_and_migrate "$store"
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
rm -rf "$(dirname "$store")"

if [ "$FAILURES" -ne 0 ]; then
  printf '\n%s assertion(s) failed in %s\n' "$FAILURES" "$(basename "${BASH_SOURCE[0]}")" >&2
  exit 1
fi
printf '\nall assertions passed in %s\n' "$(basename "${BASH_SOURCE[0]}")"
