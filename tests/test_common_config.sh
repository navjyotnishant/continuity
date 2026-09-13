#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Unit tests for lib/common.sh's continuity_config — re-read
#              behavior, store resolution (CONTINUITY_DIR vs PWD fallback),
#              metadata.json parsing tolerance, and the no-external-deps
#              contract.

# Assertion helpers are defined only when tests/run_tests.sh has not already
# supplied them, so this file runs both standalone and under that harness.
if ! type assert_eq >/dev/null 2>&1; then
	TESTS_FAILED=0
	assert_eq() {
		if [ "$1" = "$2" ]; then
			printf 'ok   %s\n' "$3"
		else
			printf 'FAIL %s: expected [%s] got [%s]\n' "$3" "$1" "$2"
			TESTS_FAILED=1
		fi
	}
	assert_ok() {
		if [ "$1" -eq 0 ]; then
			printf 'ok   %s\n' "$2"
		else
			printf 'FAIL %s: exit %s\n' "$2" "$1"
			TESTS_FAILED=1
		fi
	}
fi

TEST_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=../lib/common.sh
. "$TEST_DIR/../lib/common.sh"

FIXTURE=$(mktemp -d "${TMPDIR:-/tmp}/continuity-test.XXXXXX") && [ -d "$FIXTURE" ] || {
	printf 'FAIL could not create a temporary fixture directory\n'
	exit 1
}
trap 'rm -rf "$FIXTURE"' EXIT

# --- re-reads metadata.json on every call ------------------------------------
CONTINUITY_DIR=$(continuity_dir "$FIXTURE")
export CONTINUITY_DIR
mkdir -p "$CONTINUITY_DIR"

cat >"$CONTINUITY_DIR/metadata.json" <<'JSON'
{"retention_days": 14, "git_tracked": false}
JSON
assert_eq "14" "$(continuity_config retention_days)" \
	"continuity_config reads the initial value from metadata.json"

cat >"$CONTINUITY_DIR/metadata.json" <<'JSON'
{"retention_days": 30, "git_tracked": true}
JSON
assert_eq "30" "$(continuity_config retention_days)" \
	"continuity_config re-reads metadata.json on a later call rather than caching the first value"
assert_eq "true" "$(continuity_config git_tracked)" \
	"continuity_config re-reads git_tracked too after a mid-session edit"

# --- CONTINUITY_DIR vs PWD fallback -------------------------------------------
CUSTOM_DIR="$FIXTURE/custom/.continuity"
mkdir -p "$CUSTOM_DIR"
printf '%s' '{"retention_days": 7}' >"$CUSTOM_DIR/metadata.json"
CONTINUITY_DIR="$CUSTOM_DIR"
assert_eq "7" "$(continuity_config retention_days)" \
	"continuity_config uses CONTINUITY_DIR when set"

unset CONTINUITY_DIR
PWD_FIXTURE="$FIXTURE/pwd-project"
mkdir -p "$PWD_FIXTURE/.continuity"
printf '%s' '{"retention_days": 21}' >"$PWD_FIXTURE/.continuity/metadata.json"
ORIGINAL_DIR=$(pwd)
cd "$PWD_FIXTURE" || exit 1
PWD_RESULT=$(continuity_config retention_days)
cd "$ORIGINAL_DIR" || exit 1
assert_eq "21" "$PWD_RESULT" \
	"continuity_config falls back to resolving from PWD when CONTINUITY_DIR is not set"

# --- whitespace tolerance ------------------------------------------------------
CONTINUITY_DIR=$(continuity_dir "$FIXTURE")
cat >"$CONTINUITY_DIR/metadata.json" <<'JSON'
{
  "retention_days"   :    45  ,
  "git_tracked"  :   false
}
JSON
assert_eq "45" "$(continuity_config retention_days)" \
	"continuity_config handles whitespace around the colon and value for retention_days"
assert_eq "false" "$(continuity_config git_tracked)" \
	"continuity_config handles whitespace around the colon and value for git_tracked"

# --- additional fields ---------------------------------------------------------
cat >"$CONTINUITY_DIR/metadata.json" <<'JSON'
{
  "schema_version": "1.0",
  "plugin_version": "0.1.0",
  "created_at": "2026-09-12T00:00:00Z",
  "retention_days": 90,
  "git_tracked": true,
  "future_field": "some-value"
}
JSON
assert_eq "90" "$(continuity_config retention_days)" \
	"continuity_config finds retention_days among unrelated fields"
assert_eq "true" "$(continuity_config git_tracked)" \
	"continuity_config finds git_tracked among unrelated fields"

# --- malformed metadata.json ----------------------------------------------------
printf '%s' 'not json at all { retention_days: }}}' >"$CONTINUITY_DIR/metadata.json"
CONFIG_STDERR=$( (continuity_config retention_days >/dev/null) 2>&1 )
CONFIG_RC=$?
assert_ok "$CONFIG_RC" "continuity_config exits 0 against malformed metadata.json"
assert_eq "" "$CONFIG_STDERR" \
	"continuity_config raises no parsing errors against malformed metadata.json"
assert_eq "60" "$(continuity_config retention_days)" \
	"continuity_config falls back to the default retention_days against malformed metadata.json"

printf '\x00\x01binary garbage\xff' >"$CONTINUITY_DIR/metadata.json"
CONFIG_STDERR=$( (continuity_config git_tracked >/dev/null) 2>&1 )
CONFIG_RC=$?
assert_ok "$CONFIG_RC" "continuity_config exits 0 against binary garbage in metadata.json"
assert_eq "" "$CONFIG_STDERR" \
	"continuity_config raises no parsing errors against binary garbage in metadata.json"

# --- metadata.json as a symlink --------------------------------------------------
REAL_METADATA="$FIXTURE/real-metadata.json"
printf '%s' '{"retention_days": 5, "git_tracked": false}' >"$REAL_METADATA"
rm -f "$CONTINUITY_DIR/metadata.json"
ln -s "$REAL_METADATA" "$CONTINUITY_DIR/metadata.json"
assert_eq "5" "$(continuity_config retention_days)" \
	"continuity_config reads retention_days through a metadata.json symlink"
assert_eq "false" "$(continuity_config git_tracked)" \
	"continuity_config reads git_tracked through a metadata.json symlink"

BROKEN_TARGET="$FIXTURE/does-not-exist.json"
rm -f "$CONTINUITY_DIR/metadata.json"
ln -s "$BROKEN_TARGET" "$CONTINUITY_DIR/metadata.json"
assert_eq "60" "$(continuity_config retention_days)" \
	"continuity_config falls back to the default when metadata.json is a broken symlink"
rm -f "$CONTINUITY_DIR/metadata.json"

# --- sourced function, no external dependencies ---------------------------------
printf '%s' '{"retention_days": 12, "git_tracked": true}' >"$CONTINUITY_DIR/metadata.json"
NO_DEPS_RESULT=$(
	PATH="/usr/bin:/bin" CONTINUITY_DIR="$CONTINUITY_DIR" bash -c '
		. "'"$TEST_DIR"'/../lib/common.sh"
		continuity_config retention_days
	'
)
assert_eq "12" "$NO_DEPS_RESULT" \
	"continuity_config works as a sourced function with only coreutils on PATH, no jq or other external dependency"

exit "${TESTS_FAILED:-0}"
