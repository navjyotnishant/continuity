#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Minimal harness (assert_eq/assert_ok) discovering and running tests/test_*.sh.
#
# ponytail: no framework, just enough to run this repo's test_*.sh files and
# report pass/fail counts. Upgrade to a real runner if suites grow large.

set -u

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

FAIL_COUNT=0
PASS_COUNT=0

assert_eq() {
    local expected=$1 actual=$2 msg=${3:-}
    if [ "$expected" = "$actual" ]; then
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "FAIL: ${msg} (expected [$expected], got [$actual])"
    fi
}

assert_ok() {
    local rc=$1 msg=${2:-}
    if [ "$rc" -eq 0 ]; then
        PASS_COUNT=$((PASS_COUNT + 1))
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        echo "FAIL: ${msg} (exit code $rc)"
    fi
}

for test_file in "$TESTS_DIR"/test_*.sh; do
    [ -e "$test_file" ] || continue
    echo "== $(basename "$test_file") =="
    source "$test_file"
done

echo "---"
echo "passed: $PASS_COUNT, failed: $FAIL_COUNT"
[ "$FAIL_COUNT" -eq 0 ]
