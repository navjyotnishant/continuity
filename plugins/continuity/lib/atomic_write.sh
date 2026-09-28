#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Atomic file write (temp-then-rename) for every Continuity store write.
#
# Sourced, not executed: `. lib/atomic_write.sh` then `atomic_write <target>`.
# Contract: contracts/file-format-contract.md -> Atomicity. Targets bash 3.2.

# atomic_write <target> [content]
#
# Writes content to <target>.tmp.<pid> in the same directory as <target>, then
# mv's it onto <target>. mv within one filesystem is atomic on POSIX, so a
# reader never sees a partial file; a crash before the mv leaves only the
# orphaned .tmp.<pid> (lib/retention.sh sweeps those).
#
# Content comes from the second argument if given, else from stdin.
# Refuses to overwrite <target> with empty content (data-model.md's State Note
# rule): a trigger that produced no meaningful summary must not wipe prior
# state. Whitespace-only counts as empty -- a lone newline is that same
# no-summary case, not a deliberate write.
#
# Returns 0 on success, non-zero on empty content or a failed write/rename,
# leaving <target> untouched either way. Callers log the failure
# (lib/common.sh's continuity_log); this stays dependency-free.
atomic_write() {
    target="$1"
    if [ "$#" -ge 2 ]; then
        content="$2"
    else
        content=$(cat)
    fi

    case "$content" in
        *[![:space:]]*) ;;
        *) return 1 ;;
    esac

    tmp="${target}.tmp.$$"
    printf '%s\n' "$content" > "$tmp" || { rm -f "$tmp"; return 1; }
    mv -f "$tmp" "$target" || { rm -f "$tmp"; return 1; }
}
