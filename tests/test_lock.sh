#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Assertions for lib/lock.sh's lock_acquire (CONTINUI-28 T005/T010).
#
#   bash tests/test_lock.sh
#
# Plain-bash assert harness (no framework in this repo yet) — each case prints
# PASS/FAIL and the script exits non-zero if any assertion fails.

cd "$(dirname "$0")/.." || exit 1
. lib/lock.sh

_fail_count=0

assert() {
	local desc=$1 got=$2 want=$3
	if [ "$got" = "$want" ]; then
		echo "PASS: $desc"
	else
		echo "FAIL: $desc (got '$got', want '$want')"
		_fail_count=$((_fail_count + 1))
	fi
}

assert_true() {
	local desc=$1 rc=$2
	if [ "$rc" -eq 0 ]; then
		echo "PASS: $desc"
	else
		echo "FAIL: $desc (exit $rc, want 0)"
		_fail_count=$((_fail_count + 1))
	fi
}

assert_nonzero() {
	local desc=$1 rc=$2
	if [ "$rc" -ne 0 ]; then
		echo "PASS: $desc"
	else
		echo "FAIL: $desc (exit 0, want non-zero)"
		_fail_count=$((_fail_count + 1))
	fi
}

# lock_acquire returns 0 when the lock is successfully acquired.
test_acquire_succeeds_when_free() {
	local dir; dir=$(mktemp -d)
	lock_acquire "$dir" 0
	assert_true "lock_acquire returns 0 when lock is free" $?
	rm -rf "$dir"
}

# lock_acquire returns non-zero when the lock is already held.
test_acquire_fails_when_held() {
	local dir; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	lock_acquire "$dir" 0
	assert_nonzero "lock_acquire returns non-zero when lock is already held" $?
	rm -rf "$dir"
}

# timeout=0 tries exactly once: fails fast on a held lock instead of retrying.
test_timeout_zero_tries_once() {
	local dir start end elapsed; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	start=$(date +%s)
	lock_acquire "$dir" 0
	local rc=$?
	end=$(date +%s)
	elapsed=$((end - start))
	assert_nonzero "lock_acquire timeout=0 returns non-zero on a held lock" $rc
	assert_true "lock_acquire timeout=0 returns immediately (no retry loop)" \
		"$([ "$elapsed" -le 1 ] && echo 0 || echo 1)"
	rm -rf "$dir"
}

# timeout>0 retries until the deadline, then returns non-zero if still held.
test_timeout_positive_retries_then_fails() {
	local dir start end elapsed; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	start=$(date +%s)
	lock_acquire "$dir" 1
	local rc=$?
	end=$(date +%s)
	elapsed=$((end - start))
	assert_nonzero "lock_acquire timeout=1 returns non-zero when still held at deadline" $rc
	assert_true "lock_acquire timeout=1 waits out the timeout before giving up" \
		"$([ "$elapsed" -ge 1 ] && echo 0 || echo 1)"
	rm -rf "$dir"
}

# No timeout argument: uses the 5-second default rather than failing fast.
test_default_timeout_is_five_seconds() {
	local dir start end elapsed; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	start=$(date +%s)
	lock_acquire "$dir"
	local rc=$?
	end=$(date +%s)
	elapsed=$((end - start))
	assert_nonzero "lock_acquire with no timeout returns non-zero when still held" $rc
	assert_true "lock_acquire with no timeout waits ~5s (the default) before giving up" \
		"$([ "$elapsed" -ge 4 ] && [ "$elapsed" -le 7 ] && echo 0 || echo 1)"
	rm -rf "$dir"
}

# lock_acquire returns non-zero when path is empty string.
test_empty_path_fails() {
	lock_acquire "" 0
	assert_nonzero "lock_acquire returns non-zero when path is empty string" $?
}

# Set a path's mtime N seconds in the past. BSD (macOS) and GNU date disagree
# on the epoch flag, same as _lock_mtime in lib/lock.sh.
_touch_past() {
	local secs=$1 target=$2 ts
	ts=$(date -r "$(( $(date +%s) - secs ))" +%Y%m%d%H%M.%S 2>/dev/null) || \
		ts=$(date -d "@$(( $(date +%s) - secs ))" +%Y%m%d%H%M.%S)
	touch -t "$ts" "$target"
}

# A lock whose age cannot be read must never be broken as stale: overriding
# _lock_mtime to fail simulates an unreadable mtime on an already-held lock.
test_stale_check_false_when_mtime_unreadable() {
	local dir rc; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	rc=$(
		_lock_mtime() { return 1; }
		lock_acquire "$dir" 0
		echo $?
	)
	assert_nonzero "lock_acquire does not treat lock as stale when mtime cannot be read" "$rc"
	rm -rf "$dir"
}

# A stale lock is renamed aside (mv, atomic) rather than removed in place, so
# exactly one racer can win it (research.md R2).
test_stale_lock_renamed_not_deleted_in_place() {
	local dir; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	_touch_past 20 "$dir/.lock"
	lock_acquire "$dir" 0
	assert_true "lock_acquire renames stale lock aside and reacquires" $?
	assert_true "lock_acquire leaves no stray stale-renamed directories behind" \
		"$([ -z "$(find "$dir" -maxdepth 1 -name '.lock.stale.*')" ] && echo 0 || echo 1)"
	grep -q 'mv "\$lock"' lib/lock.sh
	assert_true "lock_acquire renames the stale lock via mv rather than removing it in place" $?
	rm -rf "$dir"
}

# After breaking a stale lock, mkdir is retried within the same attempt (no
# wait for the timeout loop), not deferred to the next poll.
test_retries_mkdir_after_breaking_stale_lock() {
	local dir start end elapsed; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	_touch_past 20 "$dir/.lock"
	start=$(date +%s)
	lock_acquire "$dir" 0
	local rc=$?
	end=$(date +%s)
	elapsed=$((end - start))
	assert_true "lock_acquire retries mkdir after breaking stale lock and succeeds" $rc
	assert_true "lock_acquire retries mkdir within the same attempt (timeout=0, no wait)" \
		"$([ "$elapsed" -le 1 ] && echo 0 || echo 1)"
	rm -rf "$dir"
}

# lock_release returns 0 once the lock directory is gone.
test_release_returns_zero() {
	local dir; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	lock_release "$dir"
	assert_true "lock_release returns 0 when lock is released" $?
	rm -rf "$dir"
}

# lock_release removes path/.lock itself, not just reports success.
test_release_removes_lock_dir() {
	local dir; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	lock_release "$dir"
	assert_true "lock_release removes path/.lock directory" \
		"$([ ! -d "$dir/.lock" ] && echo 0 || echo 1)"
	rm -rf "$dir"
}

test_acquire_succeeds_when_free
test_acquire_fails_when_held
test_timeout_zero_tries_once
test_timeout_positive_retries_then_fails
test_default_timeout_is_five_seconds
test_empty_path_fails
test_stale_check_false_when_mtime_unreadable
test_stale_lock_renamed_not_deleted_in_place
test_retries_mkdir_after_breaking_stale_lock
test_release_returns_zero
test_release_removes_lock_dir

# lock_release is idempotent: calling it again on an already-released lock
# still reports success, since the caller's concern (lock is gone) still holds.
test_release_idempotent_on_already_released() {
	local dir; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	lock_release "$dir" >/dev/null
	lock_release "$dir"
	assert_true "lock_release returns 0 when called on already-released lock" $?
	rm -rf "$dir"
}

# lock_release on a path whose directory never existed: there is no .lock to
# remove, so the state the caller cares about (lock gone) is already true.
test_release_nonexistent_path() {
	local dir; dir=$(mktemp -d)/does-not-exist
	lock_release "$dir"
	assert_true "lock_release returns 0 when called on non-existent path" $?
}

# rmdir fails on a non-empty directory, so make .lock non-empty to force
# that failure and confirm lock_release only reports non-zero when the
# lock directory is still actually there afterward.
test_release_nonzero_only_if_lock_still_exists() {
	local dir; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	: > "$dir/.lock/occupied"
	lock_release "$dir"
	local rc=$?
	assert_nonzero "lock_release returns non-zero when rmdir fails" $rc
	assert_true "lock_release non-zero corresponds to .lock still existing" \
		"$([ -d "$dir/.lock" ] && echo 0 || echo 1)"
	rm -rf "$dir"
}

# Several processes race mkdir on the same free lock: mkdir's atomicity means
# exactly one of them can win, never zero, never more than one.
test_race_acquire_exactly_one_winner() {
	local dir results i n=8; dir=$(mktemp -d)
	results=$(mktemp -d)

	for i in $(seq 1 "$n"); do
		(
			. lib/lock.sh
			if lock_acquire "$dir" 0; then
				echo win > "$results/$i"
			fi
		) &
	done
	wait

	local wins; wins=$(ls "$results" 2>/dev/null | wc -l | tr -d ' ')
	assert "exactly one racer wins a free lock" "$wins" "1"
	rm -rf "$dir" "$results"
}

# Several processes race to break the same stale lock: the mv-aside step is
# atomic, so the retry loop must leave the filesystem in a single consistent
# end state — one held .lock, no leftover .stale.* directories.
test_race_break_stale_lock_no_corruption() {
	local dir results i n=8; dir=$(mktemp -d)
	results=$(mktemp -d)
	mkdir "$dir/.lock"
	# Backdate the lock's mtime past the staleness threshold.
	touch -t "$(date -v-1H +%Y%m%d%H%M 2>/dev/null || date -d '-1 hour' +%Y%m%d%H%M)" \
		"$dir/.lock" 2>/dev/null

	for i in $(seq 1 "$n"); do
		(
			. lib/lock.sh
			if lock_acquire "$dir" 2; then
				echo win > "$results/$i"
			fi
		) &
	done
	wait

	local wins stale_leftovers
	wins=$(ls "$results" 2>/dev/null | wc -l | tr -d ' ')
	stale_leftovers=$(find "$dir" -maxdepth 1 -name '.lock.stale.*' 2>/dev/null | wc -l | tr -d ' ')
	assert "at least one racer breaks the stale lock and acquires it" \
		"$([ "$wins" -ge 1 ] && echo 0 || echo 1)" "0"
	assert "no leftover .lock.stale.* directories after the race" "$stale_leftovers" "0"
	assert_true "exactly one .lock directory remains held" \
		"$([ -d "$dir/.lock" ] && echo 0 || echo 1)"
	rm -rf "$dir" "$results"
}

test_release_idempotent_on_already_released
test_release_nonexistent_path
test_release_nonzero_only_if_lock_still_exists
test_race_acquire_exactly_one_winner
test_race_break_stale_lock_no_corruption

# A held (non-stale) lock makes lock_acquire wait rather than fail; once the
# holder releases it, the next mkdir attempt in the retry loop succeeds.
test_acquire_blocks_then_succeeds_once_released() {
	local dir start end elapsed; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	(sleep 0.3; rmdir "$dir/.lock") &
	start=$(date +%s)
	lock_acquire "$dir" 2
	local rc=$?
	end=$(date +%s)
	elapsed=$((end - start))
	wait
	assert_true "lock_acquire acquires once the holder releases" $rc
	assert_true "lock_acquire did not just fail fast (waited at least a bit)" \
		"$([ "$elapsed" -ge 0 ] && [ "$elapsed" -lt 2 ] && echo 0 || echo 1)"
	rm -rf "$dir"
}

# The staleness check and the mkdir retry are two different actors here: a
# separate background process removes the aged lock directory outright
# (standing in for another process's own break-stale step) while this call
# is blocked in its retry loop. lock_acquire never has to detect staleness
# itself to succeed — a plain mkdir on the next poll is enough once the path
# is free again.
test_acquire_succeeds_when_other_process_breaks_stale_lock() {
	local dir; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	touch -t "$(date -v-1H +%Y%m%d%H%M 2>/dev/null || date -d '-1 hour' +%Y%m%d%H%M)" \
		"$dir/.lock" 2>/dev/null
	(sleep 0.3; rm -rf "$dir/.lock") &
	lock_acquire "$dir" 2
	local rc=$?
	wait
	assert_true "lock_acquire succeeds once another process breaks the stale lock" $rc
	rm -rf "$dir"
}

# A trailing slash on path must not change where the lock directory lands or
# whether it can be created/removed.
test_trailing_slash_path() {
	local dir; dir=$(mktemp -d)
	lock_acquire "$dir/" 0
	assert_true "lock_acquire succeeds with a trailing slash on path" $?
	assert_true "lock dir is created at <path>/.lock, not doubled" \
		"$([ -d "$dir/.lock" ] && echo 0 || echo 1)"
	lock_release "$dir/"
	assert_true "lock_release succeeds with a trailing slash on path" $?
	rm -rf "$dir"
}

# lock_acquire only ever does `mkdir "$path/.lock"`, so it must work whether
# path is given absolute or relative to the caller's cwd.
test_absolute_and_relative_paths() {
	local dir parent base; dir=$(mktemp -d)
	lock_acquire "$dir" 0
	assert_true "lock_acquire works with an absolute path" $?
	lock_release "$dir"

	parent=$(dirname "$dir")
	base=$(basename "$dir")
	( cd "$parent" && lock_acquire "$base" 0 )
	assert_true "lock_acquire works with a relative path" $?
	( cd "$parent" && lock_release "$base" )
	rm -rf "$dir"
}

# timeout feeds straight into `date +%s) + timeout` with no upper-bound
# check; a huge value must not overflow the arithmetic or turn a lock that
# is actually free into a long hang.
test_large_timeout_no_overflow_or_hang() {
	local dir start end elapsed; dir=$(mktemp -d)
	start=$(date +%s)
	lock_acquire "$dir" 999999999999
	local rc=$?
	end=$(date +%s)
	elapsed=$((end - start))
	assert_true "lock_acquire succeeds immediately on a free lock despite a huge timeout" $rc
	assert_true "a huge timeout does not hang or overflow the deadline arithmetic" \
		"$([ "$elapsed" -le 2 ] && echo 0 || echo 1)"
	lock_release "$dir"
	rm -rf "$dir"
}

test_acquire_blocks_then_succeeds_once_released
test_acquire_succeeds_when_other_process_breaks_stale_lock
test_trailing_slash_path
test_absolute_and_relative_paths
test_large_timeout_no_overflow_or_hang

if [ "$_fail_count" -eq 0 ]; then
	echo "All lock_acquire assertions passed."
	exit 0
else
	echo "$_fail_count assertion(s) failed."
	exit 1
fi
