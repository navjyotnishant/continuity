#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Covers assert_ok (tests/run_tests.sh) — the zero-status and
#   non-numeric-status paths, run in a subshell so probing a deliberate
#   failure never trips this file's own EXIT trap.

. "$(cd "$(dirname "$0")" && pwd)/run_tests.sh"

RUN_TESTS_SH="$TESTS_DIR/run_tests.sh"

# --- status 0: silent, no failure recorded ----------------------------------

result=$(bash -c "
    . '$RUN_TESTS_SH'
    stderr_out=\$(assert_ok 0 'should be silent' 2>&1 >/dev/null)
    printf '%s\n%s' \"\$stderr_out\" \"\$ASSERT_FAILURES\"
")
stderr_line=$(printf '%s' "$result" | head -n 1)
failures_line=$(printf '%s' "$result" | tail -n 1)

assert_eq "" "$stderr_line" "assert_ok prints nothing when status is 0"
assert_eq "0" "$failures_line" "assert_ok does not increment ASSERT_FAILURES when status is 0"

# --- non-numeric status: fails without crashing -----------------------------

bash -c ". '$RUN_TESTS_SH'; assert_ok abc 'non-numeric status'" >/dev/null 2>&1
assert_eq "1" "$?" "assert_ok returns non-zero for a non-numeric status instead of erroring out"

non_numeric_result=$(bash -c "
    . '$RUN_TESTS_SH'
    assert_ok abc 'non-numeric status' 2>&1 >/dev/null
    printf '\n%s' \"\$ASSERT_FAILURES\"
")
non_numeric_failures=$(printf '%s' "$non_numeric_result" | tail -n 1)
assert_eq "1" "$non_numeric_failures" "assert_ok counts a non-numeric status as a failure"

printf '%s' "$non_numeric_result" | grep -qi 'integer expression'
assert_eq "1" "$?" "assert_ok does not leak the shell's own 'integer expression' error"
