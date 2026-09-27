#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Unit tests for lib/common.sh's continuity_config value
#              validation boundaries — negative/zero retention_days and
#              exact-case git_tracked — that test_common_config.sh does not
#              isolate on their own.

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
fi

TEST_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=../lib/common.sh
. "$TEST_DIR/../lib/common.sh"

FIXTURE=$(mktemp -d "${TMPDIR:-/tmp}/continuity-test.XXXXXX") && [ -d "$FIXTURE" ] || {
	printf 'FAIL could not create a temporary fixture directory\n'
	exit 1
}
trap 'rm -rf "$FIXTURE"' EXIT

CONTINUITY_DIR=$(continuity_dir "$FIXTURE")
export CONTINUITY_DIR
mkdir -p "$CONTINUITY_DIR"

# --- retention_days: negative numbers are rejected ---------------------------
printf '%s' '{"retention_days": -5, "git_tracked": true}' >"$CONTINUITY_DIR/metadata.json"
assert_eq "60" "$(continuity_config retention_days)" \
	"continuity_config rejects a negative retention_days and returns the default"

# --- retention_days: 0 is a valid value, not a falsy default trigger ---------
printf '%s' '{"retention_days": 0, "git_tracked": true}' >"$CONTINUITY_DIR/metadata.json"
assert_eq "0" "$(continuity_config retention_days)" \
	"continuity_config accepts 0 as a valid retention_days value"

# --- retention_days: a quoted, non-numeric value is rejected -----------------
printf '%s' '{"retention_days": "abc", "git_tracked": true}' >"$CONTINUITY_DIR/metadata.json"
assert_eq "60" "$(continuity_config retention_days)" \
	"continuity_config rejects a non-numeric retention_days and returns the default"

# --- git_tracked: only the exact lowercase literals are accepted -------------
# Prior line: "FALSE" differs in case from the spec's "false" and must fall
# back to the default (true) rather than being accepted case-insensitively.
printf '%s' '{"retention_days": 14, "git_tracked": "FALSE"}' >"$CONTINUITY_DIR/metadata.json"
assert_eq "true" "$(continuity_config git_tracked)" \
	"continuity_config rejects FALSE (wrong case) for git_tracked and returns the default"

printf '%s' '{"retention_days": 14, "git_tracked": "True"}' >"$CONTINUITY_DIR/metadata.json"
assert_eq "true" "$(continuity_config git_tracked)" \
	"continuity_config rejects True (wrong case) for git_tracked and returns the default"

# --- git_tracked: boolean-like values are not accepted in place of true/false
# "0" is the discriminating case: a buggy truthy/falsy parser would map it to
# "false", which would not equal the expected default of "true".
printf '%s' '{"retention_days": 14, "git_tracked": "0"}' >"$CONTINUITY_DIR/metadata.json"
assert_eq "true" "$(continuity_config git_tracked)" \
	"continuity_config rejects the boolean-like value 0 for git_tracked and returns the default"

printf '%s' '{"retention_days": 14, "git_tracked": "1"}' >"$CONTINUITY_DIR/metadata.json"
assert_eq "true" "$(continuity_config git_tracked)" \
	"continuity_config rejects the boolean-like value 1 for git_tracked and returns the default"

printf '%s' '{"retention_days": 14, "git_tracked": "yes"}' >"$CONTINUITY_DIR/metadata.json"
assert_eq "true" "$(continuity_config git_tracked)" \
	"continuity_config rejects the boolean-like value yes for git_tracked and returns the default"

exit "${TESTS_FAILED:-0}"
