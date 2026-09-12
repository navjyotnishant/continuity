#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Prunes a .continuity/ store — expired session handoffs, expired
#              errors.log lines, and orphaned .tmp.* crash debris.
#
# Sourced by lib/write_memory.sh and invoked at the end of a successful write
# (plan.md, Implementation Order step 4), so it piggybacks on an already
# backgrounded process and never touches the interactive path.
#
# Everything here fails open: a store we cannot date is a store we do not
# delete from, and retention_prune always returns 0 so a pruning problem can
# never fail its caller's write.

RETENTION_DEFAULT_DAYS=60
# Crash debris older than this is an abandoned atomic_write.sh temp file.
RETENTION_TMP_SWEEP_MINUTES=60

# Read retention_days out of metadata.json. Read fresh on every run — a
# hand-edit mid-session must take effect without a restart (data-model.md).
_retention_days() {
    local meta="$1/metadata.json" days=''
    if [ -r "$meta" ]; then
        days=$(sed -n \
            's/.*"retention_days"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' \
            "$meta" 2>/dev/null | head -n 1)
    fi
    case "$days" in
        '' | *[!0-9]*) days=$RETENTION_DEFAULT_DAYS ;;
        0) days=$RETENTION_DEFAULT_DAYS ;;
    esac
    printf '%s\n' "$days"
}

# Timestamp $1 days in the past, in date(1) format $2. BSD date (stock macOS)
# and GNU date spell relative dates differently and neither accepts the
# other's flag, so try both rather than depending on one userland.
_retention_cutoff() {
    date -u -v-"$1"d +"$2" 2>/dev/null || date -u -d "$1 days ago" +"$2" 2>/dev/null
}

# Session handoffs are dated from their filename, never from mtime — a clone
# or a checkout rewrites mtime but not the name (file-format-contract.md).
_retention_prune_sessions() {
    local dir="$1" cutoff="$2" f base stamp
    [ -d "$dir" ] || return 0
    for f in "$dir"/*.md; do
        [ -f "$f" ] || continue
        base=${f##*/}
        stamp=${base%%-*}
        case "$stamp" in
            [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z) ;;
            *) continue ;;  # not a handoff name we can date: leave it alone
        esac
        if [ "$stamp" \< "$cutoff" ]; then
            rm -f "$f" 2>/dev/null || :
        fi
    done
}

# Drop errors.log lines older than the window. A line that does not match the
# pipe-delimited four-field shape is kept, not dropped: the log must never be
# a source of a blocking failure (file-format-contract.md).
_retention_trim_log() {
    local log="$1" cutoff="$2" tmp line stamp
    [ -f "$log" ] || return 0
    tmp="$log.trim.$$"
    while IFS= read -r line || [ -n "$line" ]; do
        stamp=${line%% *}
        case "$line" in
            *' | '*' | '*' | '*)
                case "$stamp" in
                    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z)
                        if [ "$stamp" \< "$cutoff" ]; then
                            continue
                        fi
                        ;;
                esac
                ;;
        esac
        printf '%s\n' "$line"
    done <"$log" >"$tmp" 2>/dev/null && mv -f "$tmp" "$log" 2>/dev/null || rm -f "$tmp" 2>/dev/null
    return 0
}

# A .tmp.<pid> file that outlived its write is crash debris (Atomicity
# contract). Swept by mtime, which is all a temp file has.
_retention_sweep_tmp() {
    find "$1" -type f -name '*.tmp.*' -mmin "+$RETENTION_TMP_SWEEP_MINUTES" \
        -exec rm -f {} + 2>/dev/null || :
    return 0
}

# retention_prune <continuity-dir>
retention_prune() {
    local dir="$1" days cutoff_basic cutoff_extended
    [ -n "$dir" ] && [ -d "$dir" ] || return 0

    days=$(_retention_days "$dir")

    # Filename stamps are ISO-8601 basic; errors.log stamps are extended.
    # Both sort lexicographically, so a string compare is the whole test.
    cutoff_basic=$(_retention_cutoff "$days" '%Y%m%dT%H%M%SZ')
    cutoff_extended=$(_retention_cutoff "$days" '%Y-%m-%dT%H:%M:%SZ')

    # No usable date(1): prune nothing rather than guess at what is expired.
    [ -n "$cutoff_basic" ] && _retention_prune_sessions "$dir/sessions" "$cutoff_basic"
    [ -n "$cutoff_extended" ] && _retention_trim_log "$dir/errors.log" "$cutoff_extended"
    _retention_sweep_tmp "$dir"

    return 0
}
