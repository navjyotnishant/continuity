#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Unit tests for lib/common.sh's continuity_log — field shape,
#              exit-code contract on a missing/absent store, and how it
#              resolves the store directory (CONTINUITY_DIR vs PWD fallback).

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

# --- field shape -------------------------------------------------------------
CONTINUITY_DIR=$(continuity_dir "$FIXTURE")
export CONTINUITY_DIR
mkdir -p "$CONTINUITY_DIR"

continuity_log "write-decisions" "corrupted" "decisions.md truncated"
LINE=$(cat "$CONTINUITY_DIR/errors.log")
assert_eq "corrupted" "$(printf '%s' "$LINE" | cut -d'|' -f3 | sed 's/^ *//;s/ *$//')" \
	"continuity_log preserves the failure-kind parameter as the third field"
assert_eq "decisions.md truncated" "$(printf '%s' "$LINE" | cut -d'|' -f4 | sed 's/^ *//;s/ *$//')" \
	"continuity_log preserves the detail parameter as the fourth field"

# --- exit-code contract ------------------------------------------------------
rm -rf "$CONTINUITY_DIR"
mkdir -p "$CONTINUITY_DIR"
continuity_log "write-decisions" "corrupted" "second attempt"
assert_ok "$?" "continuity_log returns exit code 0 on successful append"

CONTINUITY_DIR="$FIXTURE/project/.continuity"
continuity_log "session-start-load" "missing" "no store yet" >/dev/null 2>&1
assert_ok "$?" "continuity_log returns exit code 0 when the store directory does not exist"

CONTINUITY_DIR="$FIXTURE/no-such-parent/project/.continuity"
continuity_log "session-start-load" "missing" "no parent either" >/dev/null 2>&1
assert_ok "$?" "continuity_log returns exit code 0 when the store parent directory does not exist"

# --- store resolution: CONTINUITY_DIR vs PWD fallback ------------------------
CUSTOM_DIR="$FIXTURE/custom/.continuity"
mkdir -p "$CUSTOM_DIR"
CONTINUITY_DIR="$CUSTOM_DIR"
continuity_log "write-decisions" "corrupted" "via env var"
assert_eq "1" "$(wc -l <"$CUSTOM_DIR/errors.log" | tr -d ' ')" \
	"continuity_log uses CONTINUITY_DIR environment variable when set"

unset CONTINUITY_DIR
PWD_FIXTURE="$FIXTURE/pwd-project"
mkdir -p "$PWD_FIXTURE/.continuity"
ORIGINAL_DIR=$(pwd)
cd "$PWD_FIXTURE" || exit 1
continuity_log "write-decisions" "corrupted" "via pwd fallback"
cd "$ORIGINAL_DIR" || exit 1
assert_eq "1" "$(wc -l <"$PWD_FIXTURE/.continuity/errors.log" | tr -d ' ')" \
	"continuity_log falls back to resolving from PWD when CONTINUITY_DIR is not set"

# --- creates errors.log -------------------------------------------------------
FRESH_DIR="$FIXTURE/fresh/.continuity"
mkdir -p "$FRESH_DIR"
[ ! -e "$FRESH_DIR/errors.log" ] || {
	printf 'FAIL fixture setup: errors.log already existed\n'
	TESTS_FAILED=1
}
CONTINUITY_DIR="$FRESH_DIR"
continuity_log "write-decisions" "corrupted" "first ever entry"
[ -f "$FRESH_DIR/errors.log" ]
assert_ok "$?" "continuity_log creates errors.log if it does not exist"

exit "${TESTS_FAILED:-0}"
