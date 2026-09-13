#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Covers tests/run_tests.sh itself — sourced-mode contract and
#   runner-mode "no test files found" behavior (T003).

. "$(cd "$(dirname "$0")" && pwd)/run_tests.sh"

RUN_TESTS_SH="$TESTS_DIR/run_tests.sh"

fixture=$(mktemp -d "${TMPDIR:-/tmp}/continuity-test.XXXXXX")
trap 'rm -rf "$fixture"; [ "$ASSERT_FAILURES" -eq 0 ] || exit 1' EXIT

# --- sourced mode ------------------------------------------------------------

bash -c ". \"$RUN_TESTS_SH\""
assert_ok "$?" "sourcing run_tests.sh returns 0 without running discovery"

# Expected side comes from $0, not from $TESTS_DIR — deriving it from
# $RUN_TESTS_SH would compare TESTS_DIR against itself (line 10 builds
# RUN_TESTS_SH out of TESTS_DIR), which asserts nothing.
assert_eq "$(cd "$(dirname "$0")" && pwd)" "$TESTS_DIR" \
    "sourcing sets TESTS_DIR to the tests directory path"

assert_eq "$(cd "$TESTS_DIR/.." && pwd)" "$REPO_ROOT" \
    "sourcing sets REPO_ROOT to the repository root path"

subshell_vars=$(bash -c 'printf "%s:%s" "$TESTS_DIR" "$REPO_ROOT"')
assert_eq "$TESTS_DIR:$REPO_ROOT" "$subshell_vars" \
    "TESTS_DIR and REPO_ROOT are exported so subshells can access them"

assert_eq "function" "$(type -t assert_eq)" "sourcing defines assert_eq"
assert_eq "function" "$(type -t assert_ok)" "sourcing defines assert_ok"
assert_eq "function" "$(type -t skip_test)" "sourcing defines skip_test"

bash -c ". \"$RUN_TESTS_SH\"; ASSERT_FAILURES=1"
assert_eq "1" "$?" "EXIT trap exits 1 when ASSERT_FAILURES > 0"

bash -c ". \"$RUN_TESTS_SH\"; ASSERT_FAILURES=0"
assert_eq "0" "$?" "EXIT trap exits 0 when ASSERT_FAILURES == 0"

# --- runner mode -------------------------------------------------------------

empty_dir="$fixture/empty"
mkdir -p "$empty_dir"
cp "$RUN_TESTS_SH" "$empty_dir/run_tests.sh"

runner_output=$(bash "$empty_dir/run_tests.sh" 2>&1)
runner_status=$?

assert_eq "1" "$( [ "$runner_status" -ne 0 ] && echo 1 || echo 0 )" \
    "runner mode exits non-zero when no test files found"
printf '%s' "$runner_output" | grep -qi 'no test files found'
assert_ok "$?" "runner mode prints an error message when no test files found"

# --- assert_eq ----------------------------------------------------------------

assert_eq "same" "same" "irrelevant message"
result=$?
assert_ok "$result" "assert_eq returns 0 when first and second arguments are equal"

# --- assert_eq: mismatch behavior --------------------------------------------

result=$(bash -c ". \"$RUN_TESTS_SH\"; assert_eq \"foo\" \"bar\" \"msg\" >/dev/null 2>&1; printf '%s' \$?")
assert_eq "1" "$result" "assert_eq returns 1 when arguments are not equal"

failures=$(bash -c ". \"$RUN_TESTS_SH\"; assert_eq \"foo\" \"bar\" \"msg\" >/dev/null 2>&1; printf '%s' \"\$ASSERT_FAILURES\"")
assert_eq "1" "$failures" "assert_eq increments ASSERT_FAILURES when arguments are not equal"

stderr_out=$( { bash -c ". \"$RUN_TESTS_SH\"; assert_eq \"foo\" \"bar\" \"custom message\"" >/dev/null; } 2>&1 )
printf '%s' "$stderr_out" | grep -q 'FAIL: custom message'
assert_ok "$?" "assert_eq outputs FAIL: label and message to stderr when arguments differ"

printf '%s' "$stderr_out" | grep -q 'expected: \[foo\]'
assert_ok "$?" "assert_eq outputs the expected value in the failure message"

printf '%s' "$stderr_out" | grep -q 'actual:   \[bar\]'
assert_ok "$?" "assert_eq outputs the actual value in the failure message"

# --- assert_eq: equal-arguments and empty-string behavior --------------------

out=$(bash -c ". \"$RUN_TESTS_SH\"; assert_eq \"same\" \"same\" \"msg\"" 2>&1)
assert_eq "" "$out" "assert_eq does not output anything when arguments are equal"

failures=$(bash -c ". \"$RUN_TESTS_SH\"; assert_eq \"same\" \"same\" \"msg\" >/dev/null 2>&1; printf '%s' \"\$ASSERT_FAILURES\"")
assert_eq "0" "$failures" "assert_eq does not increment ASSERT_FAILURES when arguments are equal"

result=$(bash -c ". \"$RUN_TESTS_SH\"; assert_eq \"\" \"\" \"msg\" >/dev/null 2>&1; printf '%s' \$?")
assert_eq "0" "$result" "assert_eq handles empty string comparisons as equal"

# --- assert_ok ----------------------------------------------------------------

bash -c ". \"$RUN_TESTS_SH\"; assert_ok 0 \"msg\" >/dev/null 2>&1"
assert_ok "$?" "assert_ok returns 0 when exit status argument is 0"

result=$(bash -c ". \"$RUN_TESTS_SH\"; assert_ok 1 \"msg\" >/dev/null 2>&1; printf '%s' \$?")
assert_eq "1" "$result" "assert_ok returns 1 when exit status argument is non-zero"

failures=$(bash -c ". \"$RUN_TESTS_SH\"; assert_ok 1 \"msg\" >/dev/null 2>&1; printf '%s' \"\$ASSERT_FAILURES\"")
assert_eq "1" "$failures" "assert_ok increments ASSERT_FAILURES when status is non-zero"

stderr_out=$( { bash -c ". \"$RUN_TESTS_SH\"; assert_ok 7 \"custom message\"" >/dev/null; } 2>&1 )
printf '%s' "$stderr_out" | grep -q 'FAIL: custom message (exit status 7)'
assert_ok "$?" "assert_ok outputs FAIL: label, status, and message to stderr when non-zero"
