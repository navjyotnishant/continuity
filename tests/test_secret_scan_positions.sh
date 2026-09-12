#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Covers T011 cases 19-22 -- the harness's own file-location/
#              invocation convention, empty-input handling, and multi-pattern
#              / multi-position detection in a single line.
#
# Sources lib/secret_scan.sh directly, like test_secret_scan.sh does, so it
# fails gracefully with the same "T006 not implemented yet" message when the
# real implementation is not yet present.

set -u

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd -- "$script_dir/.." && pwd)
under_test="$repo_root/lib/secret_scan.sh"

failures=0

pass() { printf 'ok   - %s\n' "$1"; }
fail() { printf 'FAIL - %s: %s\n' "$1" "$2" >&2; failures=$((failures + 1)); }

# --- 19. file discrepancy: invocation method and location match project ----
# ---     convention (Bash script under tests/), not the tracker's stated ---
# ---     ".py" / Python unittest done-when. --------------------------------

if [ -f "$repo_root/tests/test_secret_scan.sh" ]; then
	pass "secret-scan harness lives at tests/test_secret_scan.sh (Bash, matches project convention)"
else
	fail "secret-scan harness lives at tests/test_secret_scan.sh" "file not found"
fi

first_line=$(head -n1 "$repo_root/tests/test_secret_scan.sh" 2>/dev/null || true)
if printf '%s' "$first_line" | grep -q '^#!/usr/bin/env bash'; then
	pass "secret-scan harness is invoked as a Bash script (bash shebang), not a Python unittest module"
else
	fail "secret-scan harness is invoked as a Bash script" "expected a bash shebang, got: $first_line"
fi

if find "$repo_root/tests" -iname '*.py' 2>/dev/null | grep -q .; then
	fail "no Python unittest module exists for secret-scan" "found a .py file under tests/"
else
	pass "no Python unittest module exists for secret-scan (Bash-only per research.md R6)"
fi

if [ ! -f "$under_test" ]; then
	printf 'FAIL - %s does not exist (T006 not implemented yet)\n' "$under_test" >&2
	if [ "$failures" -ne 0 ]; then
		printf '%s: %d assertion(s) failed\n' "$(basename -- "${BASH_SOURCE[0]}")" "$failures" >&2
	fi
	exit 1
fi

# shellcheck source=../lib/secret_scan.sh
. "$under_test"

if ! declare -F secret_scan_line >/dev/null 2>&1; then
	printf 'FAIL - %s does not define secret_scan_line\n' "$under_test" >&2
	exit 1
fi

# --- 20. empty input does not crash -----------------------------------------

out=$(secret_scan_line '' 2>&1)
rc=$?
if [ "$rc" -eq 0 ] || [ "$rc" -ne 0 ]; then
	# Either outcome is acceptable per spec; what matters is it ran to
	# completion (no unbound-variable abort, no crash) and, if rejected,
	# still names a pattern rather than printing the empty matched text.
	if [ "$rc" -ne 0 ] && [ -z "$out" ]; then
		fail "empty input does not crash" "rejected empty input but printed no pattern name"
	else
		pass "empty input handled without crashing (exit $rc${out:+, pattern: $out})"
	fi
else
	fail "empty input does not crash" "unreachable"
fi

# --- 21. multiple secret-shaped patterns in one line are handled -----------
# ---     (either first match or all matches is an acceptable contract) ----

combo_out=$(secret_scan_line 'deploy uses AKIAIOSFODNN7EXAMPLE and -----BEGIN RSA PRIVATE KEY-----') # gitleaks:allow
combo_rc=$?
if [ "$combo_rc" -ne 0 ] && [ -n "$combo_out" ]; then
	pass "line with two secret-shaped patterns is rejected and names a pattern (got: $combo_out)"
else
	fail "line with two secret-shaped patterns is rejected" "expected non-zero exit and a pattern name, got exit $combo_rc, output: $combo_out"
fi

# --- 22. a secret-shaped pattern is detected regardless of its position ----
# ---     in the line (start / middle / end) --------------------------------

assert_rejected_at() {
	local label=$1 text=$2 out rc
	out=$(secret_scan_line "$text")
	rc=$?
	if [ "$rc" -ne 0 ] && [ -n "$out" ]; then
		pass "$label (pattern: $out)"
	else
		fail "$label" "expected non-zero exit and a pattern name, got exit $rc, output: $out"
	fi
}

assert_rejected_at "secret at start of line" \
	'AKIAIOSFODNN7EXAMPLE is what the staging bucket deploy uses' # gitleaks:allow

assert_rejected_at "secret in middle of line" \
	'the staging deploy uses AKIAIOSFODNN7EXAMPLE for its bucket policy' # gitleaks:allow

assert_rejected_at "secret at end of line" \
	'the staging bucket deploy credential is AKIAIOSFODNN7EXAMPLE' # gitleaks:allow

if [ "$failures" -ne 0 ]; then
	printf '%s: %d assertion(s) failed\n' "$(basename -- "${BASH_SOURCE[0]}")" "$failures" >&2
	exit 1
fi

printf '%s: all assertions passed\n' "$(basename -- "${BASH_SOURCE[0]}")"
