#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Meta-coverage for tests/test_common.sh itself — the sourcing,
#   skip, and fixture-lifecycle mechanics — run against copies in an isolated
#   fixture tree so it never touches the repo's real lib/ directory (T002's
#   lib/common.sh may or may not exist yet, and either way this file must
#   not perturb it).

. "$(cd "$(dirname "$0")" && pwd)/run_tests.sh"

fixture=$(mktemp -d "${TMPDIR:-/tmp}/continuity-meta-test.XXXXXX")
symbase=$(mktemp -d "${TMPDIR:-/tmp}/continuity-meta-sym.XXXXXX")
trap 'rm -rf "$fixture" "$symbase"; [ "$ASSERT_FAILURES" -eq 0 ] || exit 1' EXIT
fixture=$(cd "$fixture" && pwd -P)

mkdir -p "$fixture/tests" "$fixture/lib"
cp "$TESTS_DIR/run_tests.sh" "$fixture/tests/run_tests.sh"
cp "$TESTS_DIR/test_common.sh" "$fixture/tests/test_common.sh"

# --- lib/common.sh absent: skip path ----------------------------------------

no_lib_output=$(bash "$fixture/tests/test_common.sh" 2>&1)
no_lib_status=$?

assert_eq "0" "$no_lib_status" \
    "test_common.sh exits 0 when lib/common.sh does not exist"

printf '%s' "$no_lib_output" | grep -q '^  SKIP:'
assert_eq "0" "$?" \
    "test_common.sh skips with appropriate message when lib/common.sh does not exist"

printf '%s' "$no_lib_output" | grep -q 'lib/common.sh'
assert_eq "0" "$?" \
    "the skip message names lib/common.sh"

printf '%s' "$no_lib_output" | grep -qi 'command not found'
assert_eq "1" "$?" \
    "test_common.sh sources run_tests.sh without error (skip_test itself ran, so sourcing succeeded)"

# --- lib/common.sh present: fixture lifecycle + sourcing --------------------

cat >"$fixture/lib/common.sh" <<'EOF'
continuity_dir() { printf '%s' "stub"; }
continuity_log() { :; }
continuity_config_get() { printf '%s' "stub"; }
EOF

mkdir -p "$symbase/actual"
ln -s actual "$symbase/link"

with_lib_trace=$(TMPDIR="$symbase/link" bash -x "$fixture/tests/test_common.sh" 2>&1)

printf '%s' "$with_lib_trace" | grep -qi 'command not found.*continuity_dir'
assert_eq "1" "$?" \
    "test_common.sh sources lib/common.sh without error (continuity_dir is callable)"

printf '%s' "$with_lib_trace" | grep -qE '^\++ continuity_dir '
assert_eq "0" "$?" \
    "test_common.sh calls into the sourced lib/common.sh"

# Sanity check the fixture is a real symlink before trusting resolution
# assertions built on top of it.
assert_eq "0" "$( [ -L "$symbase/link" ] && echo 0 || echo 1 )" \
    "sanity check: symbase/link is actually a symlink"

# Pull the resolved fixture path out of the mkdir trace line rather than the
# variable-assignment trace, since that format is a stable, single-depth
# simple-command trace ("+ mkdir -p <path>/.git <path>/src/deep").
mkdir_line=$(printf '%s' "$with_lib_trace" | grep -E '^\+ mkdir -p .*/\.git ')
resolved_fixture=$(printf '%s' "$mkdir_line" | sed -E 's#^\+ mkdir -p (.*)/\.git .*#\1#')

case "$resolved_fixture" in
    */link/*) resolved_still_symlinked=yes ;;
    *) resolved_still_symlinked=no ;;
esac
assert_eq "no" "$resolved_still_symlinked" \
    "test_common.sh resolves the symlink out of the fixture path"

case "$resolved_fixture" in
    */actual/*) resolved_is_physical=yes ;;
    *) resolved_is_physical=no ;;
esac
assert_eq "yes" "$resolved_is_physical" \
    "the resolved fixture path is the symlink's physical target"

assert_eq "1" "$( [ -n "$mkdir_line" ] && echo 1 || echo 0 )" \
    "test_common.sh creates the temporary fixture directory (mkdir -p ran against it)"

assert_eq "1" "$( [ -d "$resolved_fixture" ] && echo 0 || echo 1 )" \
    "test_common.sh cleans up its fixture directory in the EXIT trap"
