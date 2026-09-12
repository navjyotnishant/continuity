#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Covers tests/test_secret_scan.sh's own exit-code and
#              reporting contract (T011) — pass/fail counting and graceful
#              handling of a missing lib/secret_scan.sh or a missing
#              secret_scan_line, plus the AWS access-key-id fixture.
#
# This test drives the harness as a subprocess against controlled temp
# copies so it can force the failure paths without touching the real
# lib/secret_scan.sh other writers depend on.

set -u

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$script_dir/.." && pwd)
harness="$repo_root/tests/test_secret_scan.sh"
real_lib="$repo_root/lib/secret_scan.sh"

failures=0

pass() { printf 'ok   - %s\n' "$1"; }
fail() { printf 'FAIL - %s: %s\n' "$1" "$2" >&2; failures=$((failures + 1)); }

# Builds a scratch repo layout (tests/test_secret_scan.sh + lib/) so the
# harness's own repo_root/under_test resolution keeps working unmodified.
make_sandbox() {
	local dir
	dir=$(mktemp -d "${TMPDIR:-/tmp}/secret_scan_test.XXXXXX")
	mkdir -p "$dir/tests" "$dir/lib"
	cp "$harness" "$dir/tests/test_secret_scan.sh"
	printf '%s\n' "$dir"
}

# --- 1. exits 0 when all assertions pass -----------------------------------

if [ -f "$real_lib" ]; then
	out=$(bash "$harness" 2>&1)
	rc=$?
	if [ "$rc" -eq 0 ]; then
		pass "exits 0 when all assertions pass"
	else
		fail "exits 0 when all assertions pass" "got exit $rc: $out"
	fi
else
	fail "exits 0 when all assertions pass" "$real_lib missing, cannot exercise the passing path (T006 not implemented yet)"
fi

# --- 2. exits 1 and reports the failure count when an assertion fails ------

sandbox=$(make_sandbox)
cat >"$sandbox/lib/secret_scan.sh" <<'EOF'
secret_scan_line() {
	# Deliberately wrong: always accepts, so every assert_rejected case
	# in the harness fails and every assert_accepted case passes.
	return 0
}
EOF
out=$(bash "$sandbox/tests/test_secret_scan.sh" 2>&1)
rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -Eq '[0-9]+ assertion\(s\) failed'; then
	pass "exits 1 and reports the failure count"
else
	fail "exits 1 and reports the failure count" "got exit $rc, output: $out"
fi
rm -rf "$sandbox"

# --- 3. fails gracefully when lib/secret_scan.sh does not exist -----------

sandbox=$(make_sandbox)
rm -rf "$sandbox/lib"
out=$(bash "$sandbox/tests/test_secret_scan.sh" 2>&1)
rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q 'does not exist' && printf '%s' "$out" | grep -q 'T006'; then
	pass "fails gracefully when lib/secret_scan.sh does not exist"
else
	fail "fails gracefully when lib/secret_scan.sh does not exist" "got exit $rc, output: $out"
fi
rm -rf "$sandbox"

# --- 4. fails gracefully when secret_scan_line is not defined -------------

sandbox=$(make_sandbox)
printf '# no secret_scan_line here\n' >"$sandbox/lib/secret_scan.sh"
out=$(bash "$sandbox/tests/test_secret_scan.sh" 2>&1)
rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q 'does not define secret_scan_line'; then
	pass "fails gracefully when secret_scan_line is not defined"
else
	fail "fails gracefully when secret_scan_line is not defined" "got exit $rc, output: $out"
fi
rm -rf "$sandbox"

# --- 5. AWS access key id pattern (AKIA...) is detected and rejected -------

if [ -f "$real_lib" ]; then
	# shellcheck source=../lib/secret_scan.sh
	. "$real_lib"
	if declare -F secret_scan_line >/dev/null 2>&1; then
		out=$(secret_scan_line 'deploy uses AKIAIOSFODNN7EXAMPLE for the staging bucket') # gitleaks:allow
		rc=$?
		if [ "$rc" -ne 0 ] && [ -n "$out" ]; then
			pass "AWS access key id pattern is detected and rejected (pattern: $out)"
		else
			fail "AWS access key id pattern is detected and rejected" "expected non-zero exit and a pattern name, got exit $rc, output: $out"
		fi
	else
		fail "AWS access key id pattern is detected and rejected" "$real_lib does not define secret_scan_line"
	fi
else
	fail "AWS access key id pattern is detected and rejected" "$real_lib missing (T006 not implemented yet)"
fi

# --- 6. rejected input that prints no pattern name is reported as a failure

sandbox=$(make_sandbox)
cat >"$sandbox/lib/secret_scan.sh" <<'EOF'
secret_scan_line() {
	# Deliberately wrong: rejects every line but never names the pattern,
	# so the harness's own assert_rejected must catch the silent rejection.
	return 1
}
EOF
out=$(bash "$sandbox/tests/test_secret_scan.sh" 2>&1)
rc=$?
if [ "$rc" -eq 1 ] && printf '%s' "$out" | grep -q 'rejected but printed no pattern name'; then
	pass "rejected input that prints no pattern name is reported as a failure"
else
	fail "rejected input that prints no pattern name is reported as a failure" "got exit $rc, output: $out"
fi
rm -rf "$sandbox"

if [ "$failures" -ne 0 ]; then
	printf '%s: %d assertion(s) failed\n' "$(basename -- "${BASH_SOURCE[0]}")" "$failures" >&2
	exit 1
fi

printf '%s: all assertions passed\n' "$(basename -- "${BASH_SOURCE[0]}")"
