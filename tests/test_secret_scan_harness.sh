#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Covers tests/test_secret_scan.sh's own accepted-input reporting,
#              path resolution, and pass-message formatting (T011 cases 15-18).
#
# This drives the harness as a subprocess -- once from the repo and once from
# an unrelated cwd -- so it never sources the real lib/secret_scan.sh directly
# and never touches it.

set -u

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$script_dir/.." && pwd)
harness="$repo_root/tests/test_secret_scan.sh"
real_lib="$repo_root/lib/secret_scan.sh"

failures=0

pass() { printf 'ok   - %s\n' "$1"; }
fail() { printf 'FAIL - %s: %s\n' "$1" "$2" >&2; failures=$((failures + 1)); }

# --- 15. accepted input exits 0 --------------------------------------------

if [ -f "$real_lib" ]; then
	bash "$harness" >/dev/null 2>&1
	rc=$?
	if [ "$rc" -eq 0 ]; then
		pass "accepted input exits 0"
	else
		fail "accepted input exits 0" "got exit $rc"
	fi
else
	fail "accepted input exits 0" "$real_lib missing, cannot exercise the passing path (T006 not implemented yet)"
fi

# --- 16. accepted input produces no diagnostic output ----------------------

if [ -f "$real_lib" ]; then
	err_out=$(bash "$harness" 2>&1 >/dev/null)
	if [ -z "$err_out" ]; then
		pass "accepted input produces no diagnostic output"
	else
		fail "accepted input produces no diagnostic output" "expected empty stderr, got: $err_out"
	fi
else
	fail "accepted input produces no diagnostic output" "$real_lib missing (T006 not implemented yet)"
fi

# --- 17. test path resolution works from any working directory ------------

if [ -f "$real_lib" ]; then
	other_dir=$(mktemp -d "${TMPDIR:-/tmp}/secret_scan_test.XXXXXX")
	out=$(cd "$other_dir" && bash "$harness" 2>&1)
	rc=$?
	if [ "$rc" -eq 0 ] && ! printf '%s' "$out" | grep -q 'does not exist'; then
		pass "test path resolution works from any working directory"
	else
		fail "test path resolution works from any working directory" "got exit $rc from cwd $other_dir, output: $out"
	fi
	rm -rf "$other_dir"
else
	fail "test path resolution works from any working directory" "$real_lib missing (T006 not implemented yet)"
fi

# --- 18. pass message for a rejected case names the matched pattern -------

if [ -f "$real_lib" ]; then
	out=$(bash "$harness" 2>&1)
	if printf '%s' "$out" | grep -Eq '^ok   - aws access key id \(pattern: [^)]+\)$'; then
		pass "output format includes pattern name in pass message for rejected cases"
	else
		fail "output format includes pattern name in pass message for rejected cases" "no matching 'ok   - <label> (pattern: <name>)' line found, output: $out"
	fi
else
	fail "output format includes pattern name in pass message for rejected cases" "$real_lib missing (T006 not implemented yet)"
fi

if [ "$failures" -ne 0 ]; then
	printf '%s: %d assertion(s) failed\n' "$(basename -- "${BASH_SOURCE[0]}")" "$failures" >&2
	exit 1
fi

printf '%s: all assertions passed\n' "$(basename -- "${BASH_SOURCE[0]}")"
