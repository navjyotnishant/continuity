#!/usr/bin/env bash
# tests/run_tests.sh — minimal, dependency-free test harness.
#
# Defines assert_eq/assert_ok, then *sources* (not executes) every
# tests/test_*.sh file so those assertion functions stay in scope. Exits
# non-zero if any assertion failed. No test framework — plain bash, per
# plan.md's Testing Strategy (research.md R6 rejected bats-core).

set -u

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export CONTINUITY_REPO_ROOT
CONTINUITY_REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

TESTS_RUN=0
TESTS_FAILED=0

# assert_eq <expected> <actual> [message]
assert_eq() {
  local expected="$1" actual="$2" msg="${3:-assert_eq}"
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ "$expected" = "$actual" ]; then
    return 0
  fi
  TESTS_FAILED=$((TESTS_FAILED + 1))
  printf 'FAIL: %s — expected [%s], got [%s]\n' "$msg" "$expected" "$actual" >&2
  return 1
}

# assert_ok <exit-status> [message]
assert_ok() {
  local status="$1" msg="${2:-assert_ok}"
  TESTS_RUN=$((TESTS_RUN + 1))
  if [ "$status" -eq 0 ]; then
    return 0
  fi
  TESTS_FAILED=$((TESTS_FAILED + 1))
  printf 'FAIL: %s — exit status %s\n' "$msg" "$status" >&2
  return 1
}

found_any=0
for t in "$SCRIPT_DIR"/test_*.sh; do
  [ -e "$t" ] || continue
  found_any=1
  echo "-- $(basename "$t")"
  . "$t"
done

if [ "$found_any" -eq 0 ]; then
  echo "no tests/test_*.sh files found" >&2
  exit 1
fi

echo "$TESTS_RUN assertions, $TESTS_FAILED failed"
[ "$TESTS_FAILED" -eq 0 ]
