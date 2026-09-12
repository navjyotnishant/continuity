#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: T031 -- meta-tests for tests/test_retention.sh itself: it
#              exists and is committed, parses cleanly, gates gracefully
#              when lib/retention.sh (T030) is absent, and builds a proper
#              .continuity/ fixture.
#
# Runs standalone: bash tests/test_retention_script.sh
# Targets bash 3.2 / BSD userland, matching test_retention.sh's own constraints.

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="$REPO_ROOT/tests/test_retention.sh"

FAILURES=0

fail() {
  echo "FAIL: $1" >&2
  FAILURES=$((FAILURES + 1))
}

# 1. Test file exists and is committed to the repository.
if [ ! -f "$TARGET" ]; then
  fail "tests/test_retention.sh does not exist"
else
  if ! ( cd "$REPO_ROOT" && git ls-files --error-unmatch tests/test_retention.sh >/dev/null 2>&1 ); then
    fail "tests/test_retention.sh exists but is not committed to git"
  fi
fi

# 2. Test script executes without syntax errors.
if [ -f "$TARGET" ]; then
  SYNTAX_ERR="$(bash -n "$TARGET" 2>&1 1>/dev/null)"
  [ -z "$SYNTAX_ERR" ] \
    || fail "tests/test_retention.sh has a syntax error: $SYNTAX_ERR"
fi

# 3. Test gracefully exits with an error when lib/retention.sh does not
# exist (T030 gate). Run a copy in an isolated fixture with no lib/ present
# at all, so this assertion holds regardless of whether T030 has landed in
# the real repo tree yet.
if [ -f "$TARGET" ]; then
  GATE_FIXTURE="$(mktemp -d "${TMPDIR:-/tmp}/continuity-retention-gate.XXXXXX")"
  mkdir -p "$GATE_FIXTURE/tests"
  cp "$TARGET" "$GATE_FIXTURE/tests/test_retention.sh"

  GATE_OUTPUT="$(bash "$GATE_FIXTURE/tests/test_retention.sh" 2>&1)"
  GATE_STATUS=$?

  rm -rf "$GATE_FIXTURE"

  if [ "$GATE_STATUS" -eq 0 ]; then
    fail "test_retention.sh exited 0 with no lib/retention.sh present (should gate with an error)"
  fi
  case "$GATE_OUTPUT" in
    *retention.sh*) : ;;
    *) fail "test_retention.sh's gate error did not mention retention.sh: $GATE_OUTPUT" ;;
  esac
fi

# 4. Test creates a temporary fixture with a proper .continuity/ directory
# structure (sessions/ plus the durable files), per the shape documented in
# file-format-contract.md.
if [ -f "$TARGET" ]; then
  grep -qF 'CONT_DIR="$FIXTURE/.continuity"' "$TARGET" \
    || fail "test_retention.sh does not build a \$FIXTURE/.continuity fixture dir"
  grep -qF 'mkdir -p "$CONT_DIR/sessions"' "$TARGET" \
    || fail "test_retention.sh does not create a .continuity/sessions/ subdirectory"
  for durable in state.md decisions.md tasks.md learnings.md metadata.json; do
    grep -qF "$durable" "$TARGET" \
      || fail "test_retention.sh fixture is missing durable file $durable"
  done
  grep -qE '"retention_days"[[:space:]]*:[[:space:]]*[0-9]+' "$TARGET" \
    || fail "test_retention.sh fixture's metadata.json has no retention_days config"
  grep -qE '[0-9]{8}T[0-9]{6}Z-[0-9]+\.md' "$TARGET" \
    || fail "test_retention.sh fixture's session files are not named with a timestamp"
fi

# 5. Test exits 0 when every assertion passes. Build an isolated copy with a
# stub lib/retention.sh that correctly prunes by filename (not mtime), so
# test_retention.sh's own fixture assertions all hold.
if [ -f "$TARGET" ]; then
  PASS_FIXTURE="$(mktemp -d "${TMPDIR:-/tmp}/continuity-retention-pass.XXXXXX")"
  mkdir -p "$PASS_FIXTURE/tests" "$PASS_FIXTURE/lib"
  cp "$TARGET" "$PASS_FIXTURE/tests/test_retention.sh"
  cat >"$PASS_FIXTURE/lib/retention.sh" <<'LIB'
retention_prune() {
  dir="$1"
  for f in "$dir"/sessions/*; do
    [ -f "$f" ] || continue
    base=$(basename "$f")
    case "$base" in
      2020*) rm -f "$f" ;;
    esac
  done
  for f in "$dir"/*.tmp.*; do
    [ -f "$f" ] || continue
    case "$f" in
      *.tmp.99999) rm -f "$f" ;;
    esac
  done
  return 0
}
LIB

  PASS_OUTPUT="$(bash "$PASS_FIXTURE/tests/test_retention.sh" 2>&1)"
  PASS_STATUS=$?
  rm -rf "$PASS_FIXTURE"

  [ "$PASS_STATUS" -eq 0 ] \
    || fail "test_retention.sh did not exit 0 against a correctly-pruning stub (status $PASS_STATUS): $PASS_OUTPUT"
fi

# 6. Test exits 1 and prints failure messages to stderr when an assertion
# fails. Same isolated copy, but the stub prunes nothing.
if [ -f "$TARGET" ]; then
  FAIL_FIXTURE="$(mktemp -d "${TMPDIR:-/tmp}/continuity-retention-fail.XXXXXX")"
  mkdir -p "$FAIL_FIXTURE/tests" "$FAIL_FIXTURE/lib"
  cp "$TARGET" "$FAIL_FIXTURE/tests/test_retention.sh"
  cat >"$FAIL_FIXTURE/lib/retention.sh" <<'LIB'
retention_prune() {
  return 0
}
LIB

  FAIL_STDERR="$(bash "$FAIL_FIXTURE/tests/test_retention.sh" 2>&1 1>/dev/null)"
  FAIL_STATUS=$?
  rm -rf "$FAIL_FIXTURE"

  [ "$FAIL_STATUS" -eq 0 ] \
    && fail "test_retention.sh exited 0 against a no-op stub that should fail assertions"
  case "$FAIL_STDERR" in
    *FAIL:*) : ;;
    *) fail "test_retention.sh's assertion failures were not printed to stderr: $FAIL_STDERR" ;;
  esac
fi

# 6b. Test actually keys pruning eligibility off the filename timestamp, not
# mtime: a stub that prunes sessions by mtime instead of filename must FAIL
# this test, because both EXPIRED_SESSION and CURRENT_SESSION are given a
# fresh mtime by test_retention.sh's own fixture -- so an mtime-based pruner
# can't tell them apart and leaves the expired one behind.
if [ -f "$TARGET" ]; then
  MTIME_FIXTURE="$(mktemp -d "${TMPDIR:-/tmp}/continuity-retention-mtime.XXXXXX")"
  mkdir -p "$MTIME_FIXTURE/tests" "$MTIME_FIXTURE/lib"
  cp "$TARGET" "$MTIME_FIXTURE/tests/test_retention.sh"
  cat >"$MTIME_FIXTURE/lib/retention.sh" <<'LIB'
retention_prune() {
  dir="$1"
  now=$(date -u +%s)
  for f in "$dir"/sessions/*; do
    [ -f "$f" ] || continue
    mtime=$(stat -f %m "$f" 2>/dev/null || stat -c %Y "$f" 2>/dev/null)
    age=$((now - mtime))
    [ "$age" -gt $((60 * 86400)) ] && rm -f "$f"
  done
  for f in "$dir"/*.tmp.*; do
    [ -f "$f" ] || continue
    case "$f" in
      *.tmp.99999) rm -f "$f" ;;
    esac
  done
  return 0
}
LIB

  MTIME_STDOUT="$(bash "$MTIME_FIXTURE/tests/test_retention.sh" 2>&1)"
  MTIME_STATUS=$?
  rm -rf "$MTIME_FIXTURE"

  [ "$MTIME_STATUS" -eq 0 ] \
    && fail "test_retention.sh passed against an mtime-keyed stub -- it should only accept filename-keyed pruning"
  case "$MTIME_STDOUT" in
    *"expired session handoff was not pruned"*) : ;;
    *) fail "mtime-keyed stub was rejected for the wrong reason: $MTIME_STDOUT" ;;
  esac
fi

# 7. Test cleans up its temporary fixture directory via a trap on EXIT,
# whether the run passes or fails. Scope TMPDIR to a throwaway dir so the
# leftover check can't be confused by anything else on the machine.
if [ -f "$TARGET" ]; then
  for stub_body in \
    'retention_prune() { for f in "$1"/sessions/*; do [ -f "$f" ] || continue; case "$(basename "$f")" in 2020*) rm -f "$f" ;; esac; done; for f in "$1"/*.tmp.*; do [ -f "$f" ] || continue; case "$f" in *.tmp.99999) rm -f "$f" ;; esac; done; return 0; }' \
    'retention_prune() { return 0; }'
  do
    TRAP_TMPDIR="$(mktemp -d "${TMPDIR:-/tmp}/continuity-retention-trap.XXXXXX")"
    TRAP_FIXTURE="$TRAP_TMPDIR/run"
    mkdir -p "$TRAP_FIXTURE/tests" "$TRAP_FIXTURE/lib"
    cp "$TARGET" "$TRAP_FIXTURE/tests/test_retention.sh"
    echo "$stub_body" >"$TRAP_FIXTURE/lib/retention.sh"

    TMPDIR="$TRAP_TMPDIR" bash "$TRAP_FIXTURE/tests/test_retention.sh" >/dev/null 2>&1

    LEFTOVER="$(find "$TRAP_TMPDIR" -maxdepth 1 -type d -name 'continuity-retention.*' 2>/dev/null)"
    [ -z "$LEFTOVER" ] \
      || fail "test_retention.sh left its fixture dir behind (trap did not fire): $LEFTOVER"

    rm -rf "$TRAP_TMPDIR"
  done
fi

# 8. Test targets bash 3.2 / BSD userland: parses under the system bash
# (3.2 on Darwin), and avoids GNU-only date arithmetic (`date -d`,
# `date --date`) and GNU-only stat flags (`stat -c`, `stat --format`).
if [ -f "$TARGET" ]; then
  BSD_SYNTAX_ERR="$(/bin/bash -n "$TARGET" 2>&1 1>/dev/null)"
  [ -z "$BSD_SYNTAX_ERR" ] \
    || fail "tests/test_retention.sh does not parse under /bin/bash (bash 3.2 on Darwin): $BSD_SYNTAX_ERR"

  if grep -Ev '^[[:space:]]*#' "$TARGET" | grep -Eq 'date[[:space:]]+(-d|--date)'; then
    fail "tests/test_retention.sh uses GNU-only 'date -d/--date' arithmetic, not portable to BSD date"
  fi
  if grep -Ev '^[[:space:]]*#' "$TARGET" | grep -Eq 'stat[[:space:]]+(-c|--format)'; then
    fail "tests/test_retention.sh uses GNU-only 'stat -c/--format', not portable to BSD stat"
  fi
fi

if [ "$FAILURES" -ne 0 ]; then
  echo "test_retention_script.sh: $FAILURES assertion(s) failed" >&2
  exit 1
fi

echo "test_retention_script.sh: ok"
