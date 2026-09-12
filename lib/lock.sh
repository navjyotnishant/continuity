#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Advisory lock for .continuity/ writes, claimed with mkdir (research.md R2).
#
# Sourced, not executed:
#
#   . lib/lock.sh
#   lock_acquire "$continuity_dir" || return 0   # unavailable: caller fails open
#   ...
#   lock_release "$continuity_dir"
#
#   lock_acquire <path> [timeout]  -> 0 once <path>/.lock is held, non-zero if
#                                     it gave up. timeout is in whole seconds;
#                                     0 means try exactly once.
#   lock_release <path>            -> 0 once <path>/.lock is gone.
#
# mkdir is the atomic claim because it either succeeds or fails in one step on
# every POSIX filesystem, with no check-then-create window and no flock(1) —
# which stock macOS does not ship (research.md R2).
#
# No `set -e` and no logging here on purpose: callers must be free to fail open,
# and the lock-unavailable log line belongs to T028.

# A lock held longer than this is treated as abandoned by a crashed process and
# broken, so a crash cannot wedge Continuity indefinitely (research.md R2).
_LOCK_STALE_SECONDS=10

# "Retry briefly" (spec.md Q5) with a concrete number. Short enough that a
# blocked write gives up long before a human notices.
_LOCK_DEFAULT_TIMEOUT=5

# Modification time in epoch seconds. BSD (macOS) and GNU stat disagree on the
# flag, so try both rather than depending on one userland.
_lock_mtime() {
	stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null
}

# 0 if the lock looks abandoned. A lock whose age cannot be read is NOT stale:
# never break a lock we cannot age.
_lock_is_stale() {
	local mtime now
	mtime=$(_lock_mtime "$1") || return 1
	[ -n "$mtime" ] || return 1
	now=$(date +%s)
	[ "$((now - mtime))" -ge "$_LOCK_STALE_SECONDS" ]
}

# POSIX only guarantees whole-second sleeps; macOS and Linux both accept
# fractions, so poll tightly where we can and fall back where we cannot.
_lock_sleep() {
	sleep 0.1 2>/dev/null || sleep 1
}

lock_acquire() {
	local path=$1 timeout=${2:-$_LOCK_DEFAULT_TIMEOUT} lock stale deadline

	# Fail fast rather than spinning out the whole timeout on a path that can
	# never accept a mkdir. Seeding .continuity/ is T029's job, not the lock's.
	[ -n "$path" ] && [ -d "$path" ] || return 1

	lock=$path/.lock
	deadline=$(( $(date +%s) + timeout ))

	while :; do
		mkdir "$lock" 2>/dev/null && return 0

		if _lock_is_stale "$lock"; then
			# Rename the stale lock aside instead of removing it in place.
			# rename() is atomic, so exactly one racer can win it; a loser's mv
			# fails on the now-absent source and therefore cannot delete the
			# fresh lock the winner has meanwhile taken. $$ alone is not unique
			# between two backgrounded subshells of one parent, hence $RANDOM.
			stale=$lock.stale.$$.$RANDOM
			if mv "$lock" "$stale" 2>/dev/null; then
				rmdir "$stale" 2>/dev/null
				mkdir "$lock" 2>/dev/null && return 0
			fi
		fi

		[ "$(date +%s)" -lt "$deadline" ] || return 1
		_lock_sleep
	done
}

lock_release() {
	local lock
	[ -n "$1" ] || return 1
	lock=$1/.lock

	rmdir "$lock" 2>/dev/null
	# Report on the state the caller cares about, not on rmdir's status: a lock
	# already broken as stale is still released, and releasing twice is not an
	# error.
	[ ! -d "$lock" ]
}
