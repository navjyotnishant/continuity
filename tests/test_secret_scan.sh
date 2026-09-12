#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Covers lib/secret_scan.sh's secret_scan_line against the four
#              secret-shaped fixtures from research.md R5 and ordinary prose.
#
# Every "secret" below is a synthetic, non-functional fixture. They are
# deliberately secret-SHAPED because that is what the unit under test must
# reject; none of them grants access to anything.

set -u

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$script_dir/.." && pwd)
under_test="$repo_root/lib/secret_scan.sh"

if [ ! -f "$under_test" ]; then
	printf 'FAIL - %s does not exist (T006 not implemented yet)\n' "$under_test" >&2
	exit 1
fi

# shellcheck source=../lib/secret_scan.sh
. "$under_test"

if ! declare -F secret_scan_line >/dev/null 2>&1; then
	printf 'FAIL - %s does not define secret_scan_line\n' "$under_test" >&2
	exit 1
fi

failures=0

pass() { printf 'ok   - %s\n' "$1"; }
fail() { printf 'FAIL - %s: %s\n' "$1" "$2" >&2; failures=$((failures + 1)); }

# A secret-shaped line must exit non-zero AND name the matched pattern on
# stdout, so errors.log can record the pattern name without the matched text.
assert_rejected() {
	local label=$1 text=$2 out rc
	out=$(secret_scan_line "$text")
	rc=$?
	if [ "$rc" -eq 0 ]; then
		fail "$label" "expected non-zero exit, got 0"
		return
	fi
	if [ -z "$out" ]; then
		fail "$label" "rejected but printed no pattern name"
		return
	fi
	pass "$label (pattern: $out)"
}

assert_accepted() {
	local label=$1 text=$2 out rc
	out=$(secret_scan_line "$text")
	rc=$?
	if [ "$rc" -ne 0 ]; then
		fail "$label" "expected exit 0, got $rc (pattern: ${out:-none})"
		return
	fi
	pass "$label"
}

# --- research.md R5: the four secret-shaped patterns -----------------------

assert_rejected "aws access key id" \
	'deploy uses AKIAIOSFODNN7EXAMPLE for the staging bucket' # gitleaks:allow

assert_rejected "assignment pattern" \
	'set api_token=hunter2hunter2hunter2 before running the hook' # gitleaks:allow

assert_rejected "pem private key header" \
	'-----BEGIN RSA PRIVATE KEY-----' # gitleaks:allow

assert_rejected "high-entropy run" \
	'signed with 9f2c4b71ae05d38c6b1f0a97e4d25c83b7a6e1f409dc52b8e37a0c9d41f6b82e' # gitleaks:allow

# --- ordinary prose must pass through untouched ---------------------------

assert_accepted "prose: decision note" \
	'Decided on plain Bash for the test harness instead of bats-core.'

assert_accepted "prose: session note" \
	'Session ended at 14:32 with three tasks still open.'

assert_accepted "prose: refactor note" \
	'Renamed the helper to continuity_log and updated its two call sites.'

if [ "$failures" -ne 0 ]; then
	printf '%s: %d assertion(s) failed\n' "$(basename -- "${BASH_SOURCE[0]}")" "$failures" >&2
	exit 1
fi

printf '%s: all assertions passed\n' "$(basename -- "${BASH_SOURCE[0]}")"
