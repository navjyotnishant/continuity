#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: T031 -- asserts lib/retention.sh prunes only expired session
#              handoffs and stale .tmp crash debris, never durable context.
#
# Runs standalone: bash tests/test_retention.sh (exits 0 once T030 exists).
# Targets bash 3.2 / BSD userland, so no `date -d` arithmetic and no GNU-only
# flags: "expired" is a fixed ancient timestamp rather than now-minus-N-days.

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RETENTION_LIB="$REPO_ROOT/lib/retention.sh"

FAILURES=0

fail() {
  echo "FAIL: $1" >&2
  FAILURES=$((FAILURES + 1))
}

assert_absent() {
  [ -e "$1" ] && fail "$2 (still present: $1)"
  return 0
}

assert_present() {
  [ -e "$1" ] || fail "$2 (missing: $1)"
  return 0
}

if [ ! -f "$RETENTION_LIB" ]; then
  echo "FAIL: $RETENTION_LIB does not exist (T030 not implemented yet)" >&2
  exit 1
fi

# shellcheck source=/dev/null
. "$RETENTION_LIB"

FIXTURE="$(mktemp -d "${TMPDIR:-/tmp}/continuity-retention.XXXXXX")"
trap 'rm -rf "$FIXTURE"' EXIT

CONT_DIR="$FIXTURE/.continuity"
mkdir -p "$CONT_DIR/sessions"

cat >"$CONT_DIR/metadata.json" <<'JSON'
{
  "schema_version": "1.0",
  "plugin_version": "0.1.0",
  "created_at": "2026-09-12T00:00:00Z",
  "retention_days": 60,
  "git_tracked": true
}
JSON

# Session handoffs. Pruning eligibility comes from the filename timestamp
# (file-format-contract.md -> Session handoff files), not mtime, so both
# fixtures are given a *fresh* mtime -- a pruner that reads mtime instead of
# the filename keeps the expired one and fails this test.
EXPIRED_SESSION="$CONT_DIR/sessions/20200101T000000Z-11111.md"
CURRENT_SESSION="$CONT_DIR/sessions/$(date -u +%Y%m%dT%H%M%SZ)-22222.md"
echo "expired handoff" >"$EXPIRED_SESSION"
echo "current handoff" >"$CURRENT_SESSION"

# Durable context. Backdated mtimes: age must never make these eligible.
for f in state.md decisions.md tasks.md learnings.md; do
  echo "durable" >"$CONT_DIR/$f"
  touch -t 202001010000 "$CONT_DIR/$f"
done
touch -t 202001010000 "$CONT_DIR/metadata.json"

# Crash debris: a .tmp.<pid> older than an hour is swept, a fresh one is not
# (it may be an in-flight atomic write).
STALE_TMP="$CONT_DIR/state.md.tmp.99999"
FRESH_TMP="$CONT_DIR/state.md.tmp.99998"
echo "orphaned" >"$STALE_TMP"
echo "in flight" >"$FRESH_TMP"
touch -t 202001010000 "$STALE_TMP"

retention_prune "$CONT_DIR"
[ $? -eq 0 ] || fail "retention_prune returned non-zero on a valid store"

assert_absent  "$EXPIRED_SESSION"  "expired session handoff was not pruned"
assert_present "$CURRENT_SESSION"  "session handoff inside the window was pruned"

for f in state.md decisions.md tasks.md learnings.md metadata.json; do
  assert_present "$CONT_DIR/$f" "durable file $f was touched by pruning"
done

assert_absent  "$STALE_TMP" "stale .tmp crash debris was not swept"
assert_present "$FRESH_TMP" "fresh .tmp file was swept while possibly in flight"

if [ "$FAILURES" -ne 0 ]; then
  echo "test_retention.sh: $FAILURES assertion(s) failed" >&2
  exit 1
fi

echo "test_retention.sh: ok"
