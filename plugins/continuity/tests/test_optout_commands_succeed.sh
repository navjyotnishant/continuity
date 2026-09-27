#!/usr/bin/env bash
# Covers docs/install.md's opt-out steps (FR-020): every documented shell
# command (echo, git rm, git commit, git status) must execute exactly as
# written, succeed, and produce the documented outcome.
set -u

FAILURES=0

assert_ok() {
  local status="$1" msg="$2"
  if [ "$status" -ne 0 ]; then
    echo "FAIL: $msg (exit status $status)"
    FAILURES=$((FAILURES + 1))
  fi
}

FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_DIR"' EXIT

cd "$FIXTURE_DIR"
git init -q
git config user.email "test@example.com"
git config user.name "Continuity Test"

# Seed .continuity/ and commit it, so step 2's "already committed" case applies.
mkdir -p .continuity
echo "state" > .continuity/state.md
git add .continuity
git commit -q -m "seed .continuity"

# --- Step 1, verbatim ---
echo '.continuity/' >> .gitignore
assert_ok "$?" "step 1: echo '.continuity/' >> .gitignore should succeed"

# --- Step 2, verbatim ---
git rm -r --cached .continuity/ >/dev/null
assert_ok "$?" "step 2: git rm -r --cached .continuity/ should succeed"

git commit -m "Stop tracking .continuity/" >/dev/null
assert_ok "$?" "step 2: git commit -m \"Stop tracking .continuity/\" should succeed"

# --- Step 3, verbatim ---
status_output="$(git status)"
assert_ok "$?" "step 3: git status should succeed"

if echo "$status_output" | grep -q '\.continuity/'; then
  echo "FAIL: git status output should not list .continuity/ as tracked or trackable"
  FAILURES=$((FAILURES + 1))
fi

if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: test_optout_commands_succeed.sh"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) in test_optout_commands_succeed.sh"
  exit 1
fi
