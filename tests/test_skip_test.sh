#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Covers skip_test (tests/run_tests.sh) — exit status, message
#   format, and that it halts the calling test file rather than just
#   returning control.

. "$(cd "$(dirname "$0")" && pwd)/run_tests.sh"

RUN_TESTS_SH="$TESTS_DIR/run_tests.sh"

# --- exits the calling file with status 0 -----------------------------------

output=$(bash -c ". '$RUN_TESTS_SH'; skip_test 'lib not ready'" 2>&1)
status=$?
assert_eq "0" "$status" "skip_test exits the test file with status 0"

# --- prints the reason with the '  SKIP: ' prefix ---------------------------

assert_eq "  SKIP: lib not ready" "$output" \
    "skip_test prints the reason prefixed with '  SKIP: '"

# --- stops execution of remaining test code ---------------------------------

after_output=$(bash -c ". '$RUN_TESTS_SH'; skip_test 'stop here'; echo SHOULD_NOT_RUN" 2>&1)
printf '%s' "$after_output" | grep -q 'SHOULD_NOT_RUN'
assert_eq "1" "$?" "skip_test stops execution of code after it in the same file"
