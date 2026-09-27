#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Covers tests/run_tests.sh runner-mode discovery/report/exit
#   behavior against a fixture tests/ dir, since test_run_tests.sh only
#   covers the sourced-mode contract and the "no test files" branch.

. "$(cd "$(dirname "$0")" && pwd)/run_tests.sh"

RUN_TESTS_SH="$TESTS_DIR/run_tests.sh"

fixture=$(mktemp -d "${TMPDIR:-/tmp}/continuity-runner-test.XXXXXX")
trap 'rm -rf "$fixture"; [ "$ASSERT_FAILURES" -eq 0 ] || exit 1' EXIT
fixture=$(cd "$fixture" && pwd -P)

mkdir -p "$fixture/tests"
cp "$RUN_TESTS_SH" "$fixture/tests/run_tests.sh"

# A file with no shebang and no +x bit: only runnable at all because the
# harness invokes it as `bash "$test_file"` rather than executing it
# directly, and $BASH_VERSION is only set when the interpreter is really
# bash (not sh/dash/zsh).
cat >"$fixture/tests/test_zz_pass.sh" <<'EOF'
printf 'stdout from pass\n'
printf 'stderr from pass\n' >&2
[ -n "$BASH_VERSION" ] && exit 0 || exit 1
EOF

cat >"$fixture/tests/test_zz_fail.sh" <<'EOF'
printf 'stdout from fail\n'
printf 'stderr from fail\n' >&2
exit 1
EOF

cat >"$fixture/tests/test_zz_skip.sh" <<EOF
. "$fixture/tests/run_tests.sh"
skip_test "fixture skip reason"
EOF

output=$(bash "$fixture/tests/run_tests.sh" 2>&1)
status=$?

# --- discovery + per-file execution/reporting -------------------------------

printf '%s' "$output" | grep -q '^PASS test_zz_pass\.sh$'
assert_ok "$?" "reports PASS for a test file that exits 0 with no SKIP output"

printf '%s' "$output" | grep -q '^FAIL test_zz_fail\.sh$'
assert_ok "$?" "reports FAIL for a test file that exits non-zero"

printf '%s' "$output" | grep -q '^SKIP test_zz_skip\.sh$'
assert_ok "$?" "reports SKIP for a test file whose output contains the SKIP pattern"

printf '%s' "$output" | grep -q 'stdout from pass'
assert_ok "$?" "prints the passing test file's captured stdout"
printf '%s' "$output" | grep -q 'stderr from pass'
assert_ok "$?" "prints the passing test file's captured stderr"
printf '%s' "$output" | grep -q 'stdout from fail'
assert_ok "$?" "prints the failing test file's captured stdout"
printf '%s' "$output" | grep -q 'stderr from fail'
assert_ok "$?" "prints the failing test file's captured stderr"

# --- counts + summary line ---------------------------------------------------

printf '%s' "$output" | grep -qE '^3 test file\(s\), 1 failed$'
assert_ok "$?" "summary line shows total test file count (3) and failed count (1)"

# --- exit status --------------------------------------------------------------

assert_eq "1" "$( [ "$status" -ne 0 ] && echo 1 || echo 0 )" \
    "runner mode exits non-zero when any test file fails"

# --- all pass/skip -> exit 0 --------------------------------------------------

rm -f "$fixture/tests/test_zz_fail.sh"
all_ok_status_output=$(bash "$fixture/tests/run_tests.sh" 2>&1)
all_ok_status=$?

assert_eq "0" "$all_ok_status" \
    "runner mode exits 0 when every remaining test file passes or skips"

printf '%s' "$all_ok_status_output" | grep -qE '^2 test file\(s\), 0 failed$'
assert_ok "$?" "summary line reflects the reduced total (2) and zero failed"
