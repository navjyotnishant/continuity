#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Test harness — assertion helpers when sourced, runs every tests/test_*.sh when executed.
#
# Two modes, one file (no separate assert library):
#
#   bash tests/run_tests.sh        discovers and runs every tests/test_*.sh,
#                                  exits non-zero if any of them fails.
#   . "$(dirname "$0")/run_tests.sh"   (from inside a test file) defines
#                                  assert_eq / assert_ok / skip_test and arms an
#                                  EXIT trap so the test file exits non-zero
#                                  when an assertion failed. Keeps each test file
#                                  runnable on its own, per T009/T010/T011.
#
# Targets bash 3.2 (macOS stock): no associative arrays, no ${var,,}, no mapfile.

TESTS_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$TESTS_DIR/.." && pwd)
export TESTS_DIR REPO_ROOT

ASSERT_FAILURES=0

# assert_eq <expected> <actual> <message>
assert_eq() {
    if [ "$1" = "$2" ]; then
        return 0
    fi
    printf '  FAIL: %s\n    expected: [%s]\n    actual:   [%s]\n' "$3" "$1" "$2" >&2
    ASSERT_FAILURES=$((ASSERT_FAILURES + 1))
    return 1
}

# assert_ok <exit-status> <message>
assert_ok() {
    if [ "$1" -eq 0 ] 2>/dev/null; then
        return 0
    fi
    printf '  FAIL: %s (exit status %s)\n' "$2" "$1" >&2
    ASSERT_FAILURES=$((ASSERT_FAILURES + 1))
    return 1
}

# skip_test <reason> — for a test whose subject module has not landed yet.
# Exits 0 so the harness stays green, but says so out loud rather than
# reporting a pass it did not earn.
skip_test() {
    printf '  SKIP: %s\n' "$1"
    exit 0
}

# Sourced by a test file: hand over the helpers and make a failed assertion
# anywhere in the file decide that file's exit status.
if [ "${BASH_SOURCE[0]}" != "$0" ]; then
    trap '[ "$ASSERT_FAILURES" -eq 0 ] || exit 1' EXIT
    return 0
fi

# ---------------------------------------------------------------- runner mode

total=0
failed=0
for test_file in "$TESTS_DIR"/test_*.sh; do
    [ -f "$test_file" ] || continue
    total=$((total + 1))
    name=$(basename "$test_file")

    output=$(bash "$test_file" 2>&1)
    status=$?

    if [ "$status" -ne 0 ]; then
        failed=$((failed + 1))
        printf 'FAIL %s\n' "$name"
    elif printf '%s' "$output" | grep -q '^  SKIP:'; then
        printf 'SKIP %s\n' "$name"
    else
        printf 'PASS %s\n' "$name"
    fi

    [ -n "$output" ] && printf '%s\n' "$output"
done

if [ "$total" -eq 0 ]; then
    printf 'No test files found in %s\n' "$TESTS_DIR" >&2
    exit 1
fi

printf '\n%s test file(s), %s failed\n' "$total" "$failed"
[ "$failed" -eq 0 ]
