#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Tests lib/lock.sh (T005) -- mutual exclusion between two
#              independent processes, contention timeout, and stale-lock
#              breaking, per research.md R2.
#
# Runs standalone: `bash tests/test_lock.sh` exits 0 when every assertion
# passes and non-zero otherwise, which is the contract tests/run_tests.sh
# discovers each tests/test_*.sh by.

TEST_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(dirname -- "$TEST_DIR")
LOCK_LIB="$REPO_ROOT/lib/lock.sh"

failures=0
pass() { printf 'ok: %s\n' "$1"; }
fail() { printf 'FAIL: %s\n' "$1" >&2; failures=$((failures + 1)); }

# Same signatures as the assertions tests/run_tests.sh (T003) defines, so a
# test reads the same whether it is run directly or by the harness.
assert_eq() { # <expected> <actual> <msg>
  if [ "$1" = "$2" ]; then pass "$3"; else fail "$3 (expected '$1', got '$2')"; fi
}
assert_ok() { # <status> <msg>
  if [ "$1" -eq 0 ]; then pass "$2"; else fail "$2 (exit $1)"; fi
}

# Reported as a value rather than a bare test so the failure message names
# what was actually on disk.
dir_state() { if [ -d "$1" ]; then echo present; else echo absent; fi; }
is_newer() { if [ "$1" -nt "$2" ]; then echo yes; else echo no; fi; }

if [ ! -f "$LOCK_LIB" ]; then
  printf 'FAIL: %s not found -- T005 is not implemented yet\n' "$LOCK_LIB" >&2
  exit 1
fi
# shellcheck source=../lib/lock.sh disable=SC1090
. "$LOCK_LIB"
# A library that turns on errexit must not abort this script on the failed
# acquires the tests below deliberately provoke.
set +e

WORK=$(mktemp -d "${TMPDIR:-/tmp}/continuity-test-lock.XXXXXX") || exit 1
trap 'rm -rf "$WORK"' EXIT

# --- Two independent processes race for the same lock ----------------------
# Exactly one wins. The loser's acquire must be refused, not granted
# alongside it -- a lock that both callers can hold is not a lock.
race_dir="$WORK/race"
results="$WORK/race-results"
mkdir -p "$race_dir" "$results"

racer() { # <name>
  if lock_acquire "$race_dir" 1; then
    printf 'acquired\n' >"$results/$1"
    sleep 2 # hold it well past the other process's timeout
    lock_release "$race_dir"
  else
    printf 'denied\n' >"$results/$1"
  fi
}

racer a &
pid_a=$!
racer b &
pid_b=$!
wait "$pid_a"
wait "$pid_b"

acquired=$(cat "$results"/* | grep -c '^acquired$')
denied=$(cat "$results"/* | grep -c '^denied$')
assert_eq 1 "$acquired" "exactly one of two racing processes acquires the lock"
assert_eq 1 "$denied" "the losing process is refused rather than granted it too"
assert_eq absent "$(dir_state "$race_dir/.lock")" "the winner's release leaves no lock behind"

# --- A contended acquire succeeds once the holder releases -----------------
wait_dir="$WORK/wait"
mkdir -p "$wait_dir"

lock_acquire "$wait_dir" 1
assert_ok "$?" "acquires an uncontended lock"

(
  sleep 1
  lock_release "$wait_dir"
) &
releaser=$!
lock_acquire "$wait_dir" 5
assert_ok "$?" "an acquire blocked by a live lock succeeds after it is released"
wait "$releaser"

lock_release "$wait_dir"
assert_eq absent "$(dir_state "$wait_dir/.lock")" "lock_release removes the lock directory"

# --- A lock older than the stale threshold is broken and re-acquired -------
# R2: a process that dies holding the lock must not wedge Continuity, so a
# lock dir older than 10s is treated as abandoned. Dated far enough back that
# no filesystem timestamp granularity can make this ambiguous.
stale_dir="$WORK/stale"
old_ref="$WORK/old.ref"
mkdir -p "$stale_dir"
: >"$old_ref"
touch -t 201001010000 "$old_ref"
mkdir "$stale_dir/.lock"
touch -t 200001010000 "$stale_dir/.lock"

lock_acquire "$stale_dir" 1
assert_ok "$?" "a lock older than the stale threshold is broken and re-acquired"
assert_eq present "$(dir_state "$stale_dir/.lock")" "the re-acquired lock directory exists"
assert_eq yes "$(is_newer "$stale_dir/.lock" "$old_ref")" "the stale lock was replaced, not adopted"
lock_release "$stale_dir"

if [ "$failures" -gt 0 ]; then
  printf '%s: %d assertion(s) failed\n' "$(basename "$0")" "$failures" >&2
  exit 1
fi
printf '%s: all assertions passed\n' "$(basename "$0")"
