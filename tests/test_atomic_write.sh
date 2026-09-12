#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Unit tests for lib/atomic_write.sh (T004) — temp-then-rename
#              durability, the empty-content refusal, and crash residue.
#
# Contract this test pins for lib/atomic_write.sh (T004):
#   source lib/atomic_write.sh
#   atomic_write <target>   # content on stdin
#     - writes stdin to "<target>.tmp.$$" in <target>'s directory, then mv's
#       it onto <target>; returns 0 and leaves no .tmp.* behind
#     - returns non-zero and leaves <target> byte-for-byte unchanged when the
#       new content is empty (data-model.md State Note validation rule)
# Content arrives on stdin rather than as an argument because the real
# callers write multi-line Markdown.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

failures=0

assert_eq() { # expected actual msg
  if [ "$1" = "$2" ]; then
    echo "ok   - $3"
  else
    echo "FAIL - $3"
    echo "         expected: [$1]"
    echo "         actual:   [$2]"
    failures=$((failures + 1))
  fi
}

assert_ok() { # status msg
  assert_eq 0 "$1" "$2"
}

assert_not_ok() { # status msg
  if [ "$1" -ne 0 ]; then
    echo "ok   - $2"
  else
    echo "FAIL - $2 (expected non-zero exit, got 0)"
    failures=$((failures + 1))
  fi
}

# Count files matching a glob without tripping over "no matches".
count_glob() {
  local n=0 f
  for f in $1; do [ -e "$f" ] && n=$((n + 1)); done
  echo "$n"
}

if [ ! -f "$REPO_ROOT/lib/atomic_write.sh" ]; then
  echo "FAIL - lib/atomic_write.sh does not exist yet (T004)"
  exit 1
fi
# shellcheck source=/dev/null
. "$REPO_ROOT/lib/atomic_write.sh"

work="$(mktemp -d "${TMPDIR:-/tmp}/test_atomic_write.XXXXXX")"
# Without this guard an unwritable TMPDIR yields work="" and every path below
# resolves against / instead, which reads as assertion failures rather than as
# a broken fixture.
if [ -z "$work" ] || [ ! -d "$work" ]; then
  echo "FAIL - could not create a temp working directory (TMPDIR=${TMPDIR:-/tmp})"
  exit 1
fi
trap 'rm -rf "$work"' EXIT

# --- 1. A write to a fresh target lands its content ------------------------
target="$work/state.md"
printf 'hello\nworld\n' | atomic_write "$target"
assert_ok "$?" "atomic_write returns 0 writing a new file"
assert_eq "$(printf 'hello\nworld')" "$(cat "$target")" "new file has the written content"

# --- 2. Overwriting replaces the content, atomically -----------------------
printf 'second version\n' | atomic_write "$target"
assert_ok "$?" "atomic_write returns 0 overwriting an existing file"
assert_eq "second version" "$(cat "$target")" "overwrite replaced the content"

# --- 3. A successful write leaves no temp file behind ----------------------
assert_eq 0 "$(count_glob "$work/state.md.tmp.*")" "no .tmp.* residue after a successful write"

# --- 4. Empty content must not wipe an existing file -----------------------
before="$(cat "$target")"
printf '' | atomic_write "$target"
assert_not_ok "$?" "atomic_write refuses empty content over an existing file"
assert_eq "$before" "$(cat "$target")" "target is unchanged after the refused empty write"
assert_eq 0 "$(count_glob "$work/state.md.tmp.*")" "no .tmp.* residue after a refused write"

# --- 5. Crash between write and rename: target intact, temp left behind ----
# Simulated directly rather than through atomic_write: this is the state a
# killed process leaves on disk, and lib/retention.sh (T031/T032) sweeps it.
crash_target="$work/decisions.md"
printf 'original content\n' > "$crash_target"
printf 'half-written repl' > "$crash_target.tmp.$$"

assert_eq "original content" "$(cat "$crash_target")" "crash leaves the original target intact"
assert_eq 1 "$(count_glob "$crash_target.tmp.*")" "crash leaves an orphaned .tmp.* file for the sweep"

echo
if [ "$failures" -eq 0 ]; then
  echo "test_atomic_write.sh: all assertions passed"
  exit 0
fi
echo "test_atomic_write.sh: $failures assertion(s) failed"
exit 1
