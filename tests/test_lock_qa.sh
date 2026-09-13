#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: QA-independent cases for lib/lock.sh not covered by tests/test_lock.sh (CONTINUI-28 T005).
#
#   bash tests/test_lock_qa.sh
#
# Same plain-bash assert harness as tests/test_lock.sh (no framework in this repo).

cd "$(dirname "$0")/.." || exit 1
. lib/lock.sh

_fail_count=0

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

_touch_past() {
	local secs=$1 target=$2 ts
	ts=$(date -r "$(( $(date +%s) - secs ))" +%Y%m%d%H%M.%S 2>/dev/null) || \
		ts=$(date -d "@$(( $(date +%s) - secs ))" +%Y%m%d%H%M.%S)
	touch -t "$ts" "$target"
}

# Acceptance case: "lock_acquire returns non-zero when path does not exist".
# Distinct from the empty-string case already covered in tests/test_lock.sh:
# this is a well-formed, non-empty path that simply has no directory there.
test_nonexistent_path_fails() {
	local parent path; parent=$(mktemp -d)
	path="$parent/does-not-exist"
	lock_acquire "$path" 0
	assert_nonzero "lock_acquire returns non-zero when path does not exist" $?
	rm -rf "$parent"
}

# Acceptance case: "lock_acquire returns non-zero when path exists but is not
# a directory". A regular file at the given path must be rejected the same
# way a missing path is, not treated as an acquirable location.
test_path_is_a_file_fails() {
	local parent path; parent=$(mktemp -d)
	path="$parent/plain-file"
	: > "$path"
	lock_acquire "$path" 0
	assert_nonzero "lock_acquire returns non-zero when path exists but is not a directory" $?
	rm -rf "$parent"
}

# Acceptance case: "lock_acquire creates path/.lock as a directory on
# successful acquisition" — asserted directly rather than inferred from a
# passing exit code, since a symlink or file named .lock would also satisfy
# a bare "it acquired" check.
test_lock_is_a_real_directory() {
	local dir; dir=$(mktemp -d)
	lock_acquire "$dir" 0
	assert_true "lock_acquire returns 0" $?
	assert_true "lock_acquire creates path/.lock as a directory" \
		"$([ -d "$dir/.lock" ] && [ ! -L "$dir/.lock" ] && echo 0 || echo 1)"
	rm -rf "$dir"
}

# Acceptance case: "lock_acquire does not break lock younger than 10
# seconds". A lock aged 5s (under _LOCK_STALE_SECONDS=10) must be left
# alone: lock_acquire fails without renaming it aside.
test_young_lock_not_broken() {
	local dir; dir=$(mktemp -d)
	mkdir "$dir/.lock"
	_touch_past 5 "$dir/.lock"
	lock_acquire "$dir" 0
	local rc=$?
	assert_nonzero "lock_acquire does not break a lock younger than 10 seconds" $rc
	assert_true "the original (young) .lock directory is still standing, untouched" \
		"$([ -d "$dir/.lock" ] && echo 0 || echo 1)"
	assert_true "no stale-rename artifact was created for a young lock" \
		"$([ -z "$(find "$dir" -maxdepth 1 -name '.lock.stale.*')" ] && echo 0 || echo 1)"
	rm -rf "$dir"
}

test_nonexistent_path_fails
test_path_is_a_file_fails
test_lock_is_a_real_directory
test_young_lock_not_broken

if [ "$_fail_count" -eq 0 ]; then
	echo "All QA lock_acquire assertions passed."
	exit 0
else
	echo "$_fail_count assertion(s) failed."
	exit 1
fi
