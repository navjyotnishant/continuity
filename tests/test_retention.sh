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
    # Old timestamp, but only three fields: not the pipe-delimited four-field
    # shape, so it must survive even though the timestamp alone is expired.
    printf '%s | orphan-field | missing-fourth-field\n' "$(stamp_days_ago 95 "$EXTENDED")"
    # Old timestamp with a non-pipe delimiter: same reasoning.
    printf '%s, csv-style, not-pipe, delimited\n' "$(stamp_days_ago 95 "$EXTENDED")"
    # Four pipe-delimited fields but an unparseable first field: not a real
    # timestamp, so the line is kept rather than treated as expired.
    printf 'not-a-timestamp | a | b | c\n'
    # Four pipe-delimited fields, all empty: malformed but must not crash the
    # trim or corrupt the file.
    printf ' |  |  | \n'
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
if grep -q 'orphan-field' "$CONT/errors.log"; then
    pass 'old-timestamped line with fewer than four pipe fields is preserved'
else
    fail 'old-timestamped line with fewer than four pipe fields is preserved'
fi
if grep -q 'csv-style' "$CONT/errors.log"; then
    pass 'old-timestamped line not using pipe delimiters is preserved'
else
    fail 'old-timestamped line not using pipe delimiters is preserved'
fi
if grep -q 'not-a-timestamp' "$CONT/errors.log"; then
    pass 'four-field pipe line with an unparseable timestamp is preserved'
else
    fail 'four-field pipe line with an unparseable timestamp is preserved'
fi
if grep -q 'session-start-load' "$CONT/errors.log" && [ -s "$CONT/errors.log" ]; then
    pass 'malformed/empty-field lines do not corrupt the log or drop valid entries'
else
    fail 'malformed/empty-field lines do not corrupt the log or drop valid entries'
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

# --- unreadable metadata.json falls back to the default -------------------

if [ "$(id -u)" -eq 0 ]; then
    printf 'ok - # SKIP unreadable metadata.json fallback (running as root, chmod is not enforced)\n'
else
    UNREADABLE="$FIXTURE/unreadable/.continuity"
    mkdir -p "$UNREADABLE/sessions"
    printf '{\n  "schema_version": "1.0",\n  "retention_days": 7,\n  "git_tracked": true\n}\n' \
        >"$UNREADABLE/metadata.json"
    chmod 000 "$UNREADABLE/metadata.json"
    UNREADABLE_KEPT="$UNREADABLE/sessions/$(stamp_days_ago 30 "$BASIC")-5555.md"
    printf 'x\n' >"$UNREADABLE_KEPT"

    retention_prune "$UNREADABLE"
    # 30 days old would die under the configured 7 days, so surviving here
    # proves the unreadable metadata.json was skipped in favor of the 60-day default.
    assert_exists "$UNREADABLE_KEPT" 'unreadable metadata.json falls back to the default retention window'
    chmod 644 "$UNREADABLE/metadata.json"
fi

# --- absent / unreadable store ---------------------------------------------

retention_prune "$FIXTURE/no-such-dir"
assert_eq 0 "$?" 'retention_prune on a missing store exits 0'
retention_prune ""
assert_eq 0 "$?" 'retention_prune with no argument exits 0'

NO_CONTINUITY_DIR="$FIXTURE/no-continuity-project"
mkdir -p "$NO_CONTINUITY_DIR"
retention_prune "$NO_CONTINUITY_DIR/.continuity"
assert_eq 0 "$?" 'retention_prune exits 0 when .continuity does not exist'

NO_SESSIONS="$FIXTURE/no-sessions/.continuity"
mkdir -p "$NO_SESSIONS"
printf '# state\n' >"$NO_SESSIONS/state.md"
retention_prune "$NO_SESSIONS"
assert_eq 0 "$?" 'retention_prune exits 0 when the sessions subdirectory does not exist'

# --- .tmp.* crash debris, exact RETENTION_TMP_SWEEP_MINUTES boundary --------

# Builds a UTC stamp, so every `touch -t` fed from it must run under TZ=UTC —
# `touch -t` reads its argument as local wall-clock time, and this fixture sits
# only 10 minutes either side of the sweep threshold, so an hours-wide timezone
# offset would decide the result instead of the code under test. UTC also has
# no DST transition to make a wall-clock time ambiguous.
stamp_minutes_ago() {
    date -u -v-"$1"M +"$2" 2>/dev/null || date -u -d "$1 minutes ago" +"$2" 2>/dev/null
}

TMPSWEEP="$FIXTURE/tmp-sweep/.continuity"
mkdir -p "$TMPSWEEP/sessions"
OLD_TMP="$TMPSWEEP/state.md.tmp.1234"
NEW_TMP="$TMPSWEEP/state.md.tmp.5678"
printf 'debris\n' >"$OLD_TMP"
printf 'debris\n' >"$NEW_TMP"
OLD_TMP_MTIME=$(stamp_minutes_ago $((RETENTION_TMP_SWEEP_MINUTES + 10)) '%Y%m%d%H%M')
NEW_TMP_MTIME=$(stamp_minutes_ago $((RETENTION_TMP_SWEEP_MINUTES - 10)) '%Y%m%d%H%M')
TZ=UTC touch -t "$OLD_TMP_MTIME" "$OLD_TMP"
TZ=UTC touch -t "$NEW_TMP_MTIME" "$NEW_TMP"

retention_prune "$TMPSWEEP"
assert_absent "$OLD_TMP" ".tmp.* debris older than RETENTION_TMP_SWEEP_MINUTES is deleted"
assert_exists "$NEW_TMP" ".tmp.* debris within RETENTION_TMP_SWEEP_MINUTES is preserved"

# --- errors.log trim is atomic ----------------------------------------------

if [ "$(id -u)" -eq 0 ]; then
    printf 'ok - # SKIP errors.log atomic trim (running as root, chmod is not enforced)\n'
else
    ATOMIC="$FIXTURE/atomic/.continuity"
    mkdir -p "$ATOMIC/sessions"
    ORIGINAL_LOG_CONTENT="$(stamp_days_ago 90 "$EXTENDED") | write-decisions | write-failed | disk full
$(stamp_days_ago 2 "$EXTENDED") | session-start-load | missing | no store"
    printf '%s\n' "$ORIGINAL_LOG_CONTENT" >"$ATOMIC/errors.log"
    # Block creation of the trim's temp file ($log.trim.$$) inside the
    # directory, forcing the write half of the atomic rename to fail before it
    # ever reaches `mv`. If trimming were not atomic, an interrupted write
    # like this could leave errors.log truncated or half-written;
    # retention_prune must still leave the original file byte-for-byte intact.
    chmod 555 "$ATOMIC"
    retention_prune "$ATOMIC"
    chmod 755 "$ATOMIC"
    AFTER_LOG_CONTENT=$(cat "$ATOMIC/errors.log")
    assert_eq "$ORIGINAL_LOG_CONTENT" "$AFTER_LOG_CONTENT" \
        'errors.log is left fully intact, not partially written, when the trim cannot complete'
fi

# --- missing errors.log ------------------------------------------------

NOLOG="$FIXTURE/nolog/.continuity"
mkdir -p "$NOLOG/sessions"
retention_prune "$NOLOG"
assert_eq 0 "$?" 'retention_prune exits 0 when errors.log does not exist'
assert_absent "$NOLOG/errors.log" 'no errors.log is created when one was never there'

# --- metadata.json fails to parse retention_days ---------------------------

BADMETA="$FIXTURE/badmeta/.continuity"
mkdir -p "$BADMETA/sessions"
printf '{\n  "schema_version": "1.0",\n  "retention_days": "not-a-number",\n  "git_tracked": true\n}\n' \
    >"$BADMETA/metadata.json"
BADMETA_KEPT="$BADMETA/sessions/$(stamp_days_ago 30 "$BASIC")-6666.md"
printf 'x\n' >"$BADMETA_KEPT"
retention_prune "$BADMETA"
assert_eq 0 "$?" 'retention_prune exits 0 when retention_days fails to parse'
# 30 days old survives only the 60-day default, so this proves the unparseable
# value was rejected in favor of the default rather than crashing the prune.
assert_exists "$BADMETA_KEPT" 'unparseable retention_days falls back to the default retention window'

# --- no usable date(1) ------------------------------------------------------

NODATE="$FIXTURE/nodate/.continuity"
mkdir -p "$NODATE/sessions"
NODATE_SESSION="$NODATE/sessions/$(stamp_days_ago 90 "$BASIC")-7777.md"
printf 'x\n' >"$NODATE_SESSION"

(
    # Shadow date(1) with a function that always fails, as if the host had no
    # usable date command. Confined to this subshell.
    date() { return 1; }
    retention_prune "$NODATE"
)
assert_eq 0 "$?" 'retention_prune exits 0 when date(1) cannot compute relative dates'
assert_exists "$NODATE_SESSION" 'nothing is pruned when date(1) cannot compute relative dates'

# --- durable files survive an aggressive prune ------------------------------

DURABLE="$FIXTURE/durable-check/.continuity"
mkdir -p "$DURABLE/sessions"
printf '{\n  "schema_version": "1.0",\n  "retention_days": 1,\n  "git_tracked": true\n}\n' \
    >"$DURABLE/metadata.json"
for f in state.md decisions.md tasks.md learnings.md; do
    printf '# %s\n' "$f" >"$DURABLE/$f"
    touch -t 200001010000 "$DURABLE/$f"
done
retention_prune "$DURABLE"
for f in state.md decisions.md tasks.md learnings.md; do
    assert_exists "$DURABLE/$f" "durable $f survives even a 1-day retention window"
done

# --- retention_days=0 falls back to the default ----------------------------

ZERO="$FIXTURE/zero-days/.continuity"
mkdir -p "$ZERO/sessions"
printf '{\n  "schema_version": "1.0",\n  "retention_days": 0,\n  "git_tracked": true\n}\n' \
    >"$ZERO/metadata.json"
ZERO_KEPT="$ZERO/sessions/$(stamp_days_ago 30 "$BASIC")-1010.md"
printf 'x\n' >"$ZERO_KEPT"
retention_prune "$ZERO"
# A literal 0-day window would prune everything immediately. Survival at 30
# days only makes sense if 0 was rejected in favor of the 60-day default.
assert_exists "$ZERO_KEPT" 'retention_days=0 falls back to the default retention window'

# --- invalid retention_days (non-numeric, negative) falls back to the default

NEG="$FIXTURE/negative-days/.continuity"
mkdir -p "$NEG/sessions"
printf '{\n  "schema_version": "1.0",\n  "retention_days": -5,\n  "git_tracked": true\n}\n' \
    >"$NEG/metadata.json"
NEG_KEPT="$NEG/sessions/$(stamp_days_ago 30 "$BASIC")-2020.md"
printf 'x\n' >"$NEG_KEPT"
retention_prune "$NEG"
assert_exists "$NEG_KEPT" 'negative retention_days falls back to the default retention window'

NONNUM="$FIXTURE/nonnumeric-days/.continuity"
mkdir -p "$NONNUM/sessions"
printf '{\n  "schema_version": "1.0",\n  "retention_days": "sixty",\n  "git_tracked": true\n}\n' \
    >"$NONNUM/metadata.json"
NONNUM_KEPT="$NONNUM/sessions/$(stamp_days_ago 30 "$BASIC")-3030.md"
printf 'x\n' >"$NONNUM_KEPT"
retention_prune "$NONNUM"
assert_exists "$NONNUM_KEPT" 'non-numeric retention_days falls back to the default retention window'

# --- hand-edited metadata.json takes effect without a restart ---------------

LIVE="$FIXTURE/live-edit/.continuity"
mkdir -p "$LIVE/sessions"
printf '{\n  "schema_version": "1.0",\n  "retention_days": 60,\n  "git_tracked": true\n}\n' \
    >"$LIVE/metadata.json"
LIVE_SESSION="$LIVE/sessions/$(stamp_days_ago 10 "$BASIC")-4040.md"
printf 'x\n' >"$LIVE_SESSION"
retention_prune "$LIVE"
assert_exists "$LIVE_SESSION" 'session inside the original 60-day window is kept'
# Hand-edit metadata.json in place, mid-session, no restart of anything.
printf '{\n  "schema_version": "1.0",\n  "retention_days": 7,\n  "git_tracked": true\n}\n' \
    >"$LIVE/metadata.json"
retention_prune "$LIVE"
assert_absent "$LIVE_SESSION" \
    'a hand-edit to metadata.json takes effect on the very next retention_prune call, no restart needed'

# --- BSD date and GNU date both compute correct relative cutoffs ------------

# Simulate a GNU-only host: BSD's -v flag is rejected, forcing the -d
# fallback. The GNU-shaped call is answered by delegating to the real (BSD)
# date under the hood, so this proves retention_prune's -d branch is reached
# and its output is consumed correctly, independent of what userland is
# actually installed on this test host.
GNUHOST="$FIXTURE/gnu-host/.continuity"
mkdir -p "$GNUHOST/sessions"
GNUHOST_OLD="$GNUHOST/sessions/$(stamp_days_ago 90 "$BASIC")-5050.md"
GNUHOST_NEW="$GNUHOST/sessions/$(stamp_days_ago 3 "$BASIC")-6060.md"
printf 'x\n' >"$GNUHOST_OLD"
printf 'x\n' >"$GNUHOST_NEW"
(
    date() {
        local a n fmt
        for a in "$@"; do
            case "$a" in -v-*) return 1 ;; esac
        done
        while [ "$#" -gt 0 ]; do
            case "$1" in
                -d) shift; n=${1%% *} ;;
                +*) fmt=${1#+} ;;
            esac
            shift
        done
        command date -u -v-"${n}"d "+$fmt"
    }
    retention_prune "$GNUHOST"
)
assert_absent "$GNUHOST_OLD" \
    'retention_prune prunes correctly when only GNU-style date -d is available'
assert_exists "$GNUHOST_NEW" \
    'retention_prune keeps a recent session when only GNU-style date -d is available'

# Simulate a BSD-only host: GNU's -d flag is rejected, so only -v is ever
# exercised (the branch most other tests in this file already run on a real
# BSD host, but is named explicitly here for the dual-userland contract).
BSDHOST="$FIXTURE/bsd-host/.continuity"
mkdir -p "$BSDHOST/sessions"
BSDHOST_OLD="$BSDHOST/sessions/$(stamp_days_ago 90 "$BASIC")-7070.md"
BSDHOST_NEW="$BSDHOST/sessions/$(stamp_days_ago 3 "$BASIC")-8080.md"
printf 'x\n' >"$BSDHOST_OLD"
printf 'x\n' >"$BSDHOST_NEW"
(
    date() {
        local a
        for a in "$@"; do
            case "$a" in -d) return 1 ;; esac
        done
        command date "$@"
    }
    retention_prune "$BSDHOST"
)
assert_absent "$BSDHOST_OLD" \
    'retention_prune prunes correctly when only BSD-style date -v is available'
assert_exists "$BSDHOST_NEW" \
    'retention_prune keeps a recent session when only BSD-style date -v is available'

# --- exact cutoff boundary: stamp == cutoff is kept, one second older is pruned

# retention_prune compares with a strict `<`, so an entry exactly AT the
# cutoff must survive and one one second older must not. Shadowing date(1) to
# return a fixed cutoff (ignoring -v/-d flags) makes this deterministic
# instead of racing the real clock.
BOUNDARY="$FIXTURE/boundary/.continuity"
mkdir -p "$BOUNDARY/sessions"
FIXED_CUTOFF_BASIC='20200101T000000Z'
FIXED_CUTOFF_EXTENDED='2020-01-01T00:00:00Z'
AT_CUTOFF_SESSION="$BOUNDARY/sessions/${FIXED_CUTOFF_BASIC}-9090.md"
PAST_CUTOFF_SESSION="$BOUNDARY/sessions/20191231T235959Z-9191.md"
printf 'x\n' >"$AT_CUTOFF_SESSION"
printf 'x\n' >"$PAST_CUTOFF_SESSION"
{
    printf '%s | at-cutoff | probe | probe\n' "$FIXED_CUTOFF_EXTENDED"
    printf '2019-12-31T23:59:59Z | past-cutoff | probe | probe\n'
} >"$BOUNDARY/errors.log"

(
    date() {
        local a fmt=''
        for a in "$@"; do
            case "$a" in +*) fmt=${a#+} ;; esac
        done
        case "$fmt" in
            '%Y%m%dT%H%M%SZ') printf '%s\n' "$FIXED_CUTOFF_BASIC" ;;
            '%Y-%m-%dT%H:%M:%SZ') printf '%s\n' "$FIXED_CUTOFF_EXTENDED" ;;
            *) command date "$@" ;;
        esac
    }
    retention_prune "$BOUNDARY"
)
assert_exists "$AT_CUTOFF_SESSION" 'session timestamped exactly at the cutoff is kept, not pruned'
assert_absent "$PAST_CUTOFF_SESSION" 'session one second older than the cutoff is pruned'
if grep -q 'at-cutoff' "$BOUNDARY/errors.log"; then
    pass 'errors.log line timestamped exactly at the cutoff is kept, not trimmed'
else
    fail 'errors.log line timestamped exactly at the cutoff is kept, not trimmed'
fi
if grep -q 'past-cutoff' "$BOUNDARY/errors.log"; then
    fail 'errors.log line one second older than the cutoff is trimmed'
else
    pass 'errors.log line one second older than the cutoff is trimmed'
fi

if [ "$FAILURES" -ne 0 ]; then
    printf '%s assertion(s) failed\n' "$FAILURES" >&2
    exit 1
fi
printf 'all retention assertions passed\n'
