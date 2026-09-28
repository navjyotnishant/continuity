#!/usr/bin/env bash
# Covers docs/install.md's opt-out step 1 (FR-020): once '.continuity/' is
# added to .gitignore, arbitrary files nested under it — not just top-level
# ones — must be ignored by git.
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

# Documented opt-out step, verbatim.
echo '.continuity/' >> .gitignore

# Arbitrary nested files under .continuity/, not just a top-level one.
mkdir -p .continuity/a/b/c
echo "nested" > .continuity/a/b/c/file.txt
echo "shallow" > .continuity/state.md

status="$(git status --porcelain)"
assert_eq "" "$([[ "$status" == *".continuity"* ]] && echo "leaked")" \
  "nested .continuity/ files must not appear in git status"

git check-ignore -q .continuity/a/b/c/file.txt
assert_ok "$?" "git check-ignore should report .continuity/a/b/c/file.txt as ignored"

git check-ignore -q .continuity/state.md
assert_ok "$?" "git check-ignore should report .continuity/state.md as ignored"

git add -A
staged="$(git diff --cached --name-only)"
assert_eq "" "$([[ "$staged" == *".continuity"* ]] && echo "leaked")" \
  "git add -A must not stage anything under .continuity/"

if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: test_gitignore_nested.sh"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) in test_gitignore_nested.sh"
  exit 1
fi
