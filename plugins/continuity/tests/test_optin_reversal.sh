#!/usr/bin/env bash
# Covers docs/install.md's opt-out being reversible (FR-020): a project that
# opted out can opt back in by removing the .gitignore entry and re-adding
# .continuity/ — the files must become tracked again.
set -u

FAILURES=0

assert_ok() {
  local status="$1" msg="$2"
  if [ "$status" -ne 0 ]; then
    echo "FAIL: $msg (exit status $status)"
    FAILURES=$((FAILURES + 1))
  fi
}

assert_eq() {
  local expected="$1" actual="$2" msg="$3"
  if [ "$expected" != "$actual" ]; then
    echo "FAIL: $msg (expected [$expected], got [$actual])"
    FAILURES=$((FAILURES + 1))
  fi
}

FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_DIR"' EXIT

cd "$FIXTURE_DIR"
git init -q
git config user.email "test@example.com"
git config user.name "Continuity Test"

mkdir -p .continuity
echo "state" > .continuity/state.md
git add .continuity
git commit -q -m "seed .continuity"

# Opt out, per docs/install.md.
echo '.continuity/' >> .gitignore
git rm -r --cached .continuity/ >/dev/null
git add .gitignore
git commit -q -m "Stop tracking .continuity/"

tracked_after_optout="$(git ls-files .continuity)"
assert_eq "" "$tracked_after_optout" \
  "sanity check: .continuity/ should be untracked right after opt-out"

# Opt back in: remove the ignore rule, then re-add.
grep -v '^\.continuity/$' .gitignore > .gitignore.tmp
mv .gitignore.tmp .gitignore

git add .continuity/
assert_ok "$?" "git add .continuity/ should succeed after removing the ignore rule"

staged="$(git diff --cached --name-only)"
assert_ok "$([[ "$staged" == *".continuity/state.md"* ]] && echo 0 || echo 1)" \
  ".continuity/state.md should be staged after opting back in"

git commit -q -m "Resume tracking .continuity/"
assert_ok "$?" "commit after re-adding .continuity/ should succeed"

tracked_after_optin="$(git ls-files .continuity)"
assert_ok "$([[ "$tracked_after_optin" == *".continuity/state.md"* ]] && echo 0 || echo 1)" \
  ".continuity/state.md should be tracked again after opting back in"

if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: test_optin_reversal.sh"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) in test_optin_reversal.sh"
  exit 1
fi
