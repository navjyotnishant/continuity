#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Unit tests for lib/retention.sh (session pruning, errors.log
#              trimming, .tmp.* sweeping). Runnable standalone: exits non-zero
#              if any assertion fails.

TEST_DIR=$(cd "$(dirname "$0")" && pwd)
REPO_ROOT=$(dirname "$TEST_DIR")
# shellcheck source=../lib/retention.sh
. "$REPO_ROOT/lib/retention.sh"

FAILURES=0

fail() {
    FAILURES=$((FAILURES + 1))
    printf 'not ok - %s\n' "$1" >&2
}

pass() { printf 'ok - %s\n' "$1"; }

assert_exists() {
    if [ -e "$1" ]; then pass "$2"; else fail "$2 (missing: $1)"; fi
}

assert_absent() {
    if [ -e "$1" ]; then fail "$2 (still present: $1)"; else pass "$2"; fi
}

assert_eq() {
    if [ "$1" = "$2" ]; then pass "$3"; else fail "$3 (expected [$1], got [$2])"; fi
}

# Same dual-userland dance as retention.sh: BSD date first, then GNU.
stamp_days_ago() {
    date -u -v-"$1"d +"$2" 2>/dev/null || date -u -d "$1 days ago" +"$2" 2>/dev/null
}

FIXTURE=$(mktemp -d "${TMPDIR:-/tmp}/test_retention.XXXXXX") || exit 1
trap 'rm -rf "$FIXTURE"' EXIT
CONT="$FIXTURE/.continuity"
mkdir -p "$CONT/sessions"

BASIC='%Y%m%dT%H%M%SZ'
EXTENDED='%Y-%m-%dT%H:%M:%SZ'

if [ -z "$(stamp_days_ago 1 "$BASIC")" ]; then
    printf 'not ok - no usable date(1) for relative dates on this host\n' >&2
    exit 1
fi

# --- fixture ---------------------------------------------------------------

OLD_SESSION="$CONT/sessions/$(stamp_days_ago 90 "$BASIC")-1111.md"
NEW_SESSION="$CONT/sessions/$(stamp_days_ago 3 "$BASIC")-2222.md"
UNDATED_SESSION="$CONT/sessions/not-a-handoff.md"
printf 'old handoff\n' >"$OLD_SESSION"
printf 'recent handoff\n' >"$NEW_SESSION"
printf 'unparseable name\n' >"$UNDATED_SESSION"
# Fresh mtimes on both, so anything that passes here read the filename and not
# the mtime — the whole point of the filename-dated contract.
touch "$OLD_SESSION" "$NEW_SESSION" "$UNDATED_SESSION"

for f in state.md decisions.md tasks.md learnings.md; do
    printf '# %s\n' "$f" >"$CONT/$f"
    touch -t 200001010000 "$CONT/$f"   # far older than any retention window
done

printf 'crash debris\n' >"$CONT/state.md.tmp.9999"
touch -t 200001010000 "$CONT/state.md.tmp.9999"
printf 'in-flight write\n' >"$CONT/decisions.md.tmp.8888"

{
    printf '%s | write-decisions | write-failed | disk full\n' "$(stamp_days_ago 90 "$EXTENDED")"
    printf '%s | session-start-load | missing | no store\n' "$(stamp_days_ago 2 "$EXTENDED")"
    printf 'garbage line with no fields\n'
} >"$CONT/errors.log"

# --- run -------------------------------------------------------------------

retention_prune "$CONT"
assert_eq 0 "$?" 'retention_prune exits 0'

# --- sessions --------------------------------------------------------------

assert_absent "$OLD_SESSION" 'session older than the window is pruned'
assert_exists "$NEW_SESSION" 'session inside the window is kept'
assert_exists "$UNDATED_SESSION" 'session with an undateable name is kept'

# --- durable files ---------------------------------------------------------

for f in state.md decisions.md tasks.md learnings.md; do
    assert_exists "$CONT/$f" "durable $f is never pruned regardless of age"
done

# --- crash debris ----------------------------------------------------------

assert_absent "$CONT/state.md.tmp.9999" 'stale .tmp.* file is swept'
assert_exists "$CONT/decisions.md.tmp.8888" 'fresh .tmp.* file is left in place'

# --- errors.log ------------------------------------------------------------

if grep -q 'write-decisions' "$CONT/errors.log"; then
    fail 'errors.log line older than the window is trimmed'
else
    pass 'errors.log line older than the window is trimmed'
fi
if grep -q 'session-start-load' "$CONT/errors.log"; then
    pass 'errors.log line inside the window is kept'
else
    fail 'errors.log line inside the window is kept'
fi
if grep -q 'garbage line' "$CONT/errors.log"; then
    pass 'malformed errors.log line is kept, not treated as expired'
else
    fail 'malformed errors.log line is kept, not treated as expired'
fi

# --- retention_days honored from metadata.json -----------------------------

CONF="$FIXTURE/configured/.continuity"
mkdir -p "$CONF/sessions"
printf '{\n  "schema_version": "1.0",\n  "retention_days": 7,\n  "git_tracked": true\n}\n' \
    >"$CONF/metadata.json"
SHORT_EXPIRED="$CONF/sessions/$(stamp_days_ago 30 "$BASIC")-3333.md"
SHORT_KEPT="$CONF/sessions/$(stamp_days_ago 2 "$BASIC")-4444.md"
printf 'x\n' >"$SHORT_EXPIRED"
printf 'x\n' >"$SHORT_KEPT"

retention_prune "$CONF"
# 30 days old survives the 60-day default and dies under the configured 7, so
# this only passes if metadata.json was actually read.
assert_absent "$SHORT_EXPIRED" 'configured retention_days shortens the window'
assert_exists "$SHORT_KEPT" 'configured retention_days keeps a recent session'

# --- absent / unreadable store ---------------------------------------------

retention_prune "$FIXTURE/no-such-dir"
assert_eq 0 "$?" 'retention_prune on a missing store exits 0'
retention_prune ""
assert_eq 0 "$?" 'retention_prune with no argument exits 0'

if [ "$FAILURES" -ne 0 ]; then
    printf '%s assertion(s) failed\n' "$FAILURES" >&2
    exit 1
fi
printf 'all retention assertions passed\n'
