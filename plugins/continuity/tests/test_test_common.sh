#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-13
# Description: Meta-coverage for tests/test_common.sh itself — sourcing
#   lib/common.sh and the fixture lifecycle — run against a copy in an
#   isolated fixture tree so it never touches the repo's real lib/ directory.
#
# Rewritten (CONTINUI-26 merge, 2026-09-13): the version this replaced
# asserted on a skip-when-lib-absent path and a symlink-resolving fixture
# that test_common.sh no longer has -- it now sources lib/common.sh
# unconditionally (lib/common.sh is a required file by this point in the
# project, not an optional one to skip around) and builds its fixture with
# a plain `mktemp -d`, no symlink involved. Every assertion below checks
# what the current test_common.sh actually does.

. "$(cd "$(dirname "$0")" && pwd)/run_tests.sh"

fixture=$(mktemp -d "${TMPDIR:-/tmp}/continuity-meta-test.XXXXXX")
trap 'rm -rf "$fixture"; [ "$ASSERT_FAILURES" -eq 0 ] || exit 1' EXIT
fixture=$(cd "$fixture" && pwd -P)

mkdir -p "$fixture/tests" "$fixture/lib"
cp "$TESTS_DIR/run_tests.sh" "$fixture/tests/run_tests.sh"
cp "$TESTS_DIR/test_common.sh" "$fixture/tests/test_common.sh"
# The REAL lib/common.sh, not a hand-rolled stub: this meta-test's job is
# sourcing/fixture-lifecycle mechanics, not re-deciding common.sh's own
# contract, and a stub drifts from that contract the moment it changes.
cp "$TESTS_DIR/../lib/common.sh" "$fixture/lib/common.sh"

output=$(bash "$fixture/tests/test_common.sh" 2>&1)
status=$?

assert_eq "0" "$status" \
	"test_common.sh exits 0 against a working lib/common.sh"

printf '%s' "$output" | grep -qi 'command not found'
assert_eq "1" "$?" \
	"test_common.sh sources lib/common.sh and run_tests.sh without a command-not-found error"

printf '%s' "$output" | grep -q '^FAIL'
assert_eq "1" "$?" \
	"every assertion in test_common.sh passes against a correct lib/common.sh"

# The fixture test_common.sh creates for ITSELF (under $TMPDIR) must be
# cleaned up by its own EXIT trap -- this run must not leak a
# continuity-test.* directory into the real temp dir.
leftover=$(find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'continuity-test.*' -newer "$fixture/tests/test_common.sh" 2>/dev/null)
assert_eq "" "$leftover" \
	"test_common.sh cleans up its own fixture directory in the EXIT trap"
