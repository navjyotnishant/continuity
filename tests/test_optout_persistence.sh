#!/usr/bin/env bash
# Covers docs/install.md's opt-out steps (Scenario 5, FR-020): after a
# project follows the documented .gitignore + `git rm -r --cached` steps,
# Continuity must keep creating, reading, and modifying .continuity/ files
# exactly as before — the opt-out is a version-control decision only.
set -u

FAILURES=0

assert_eq() {
  local expected="$1" actual="$2" msg="$3"
  if [ "$expected" != "$actual" ]; then
    echo "FAIL: $msg (expected [$expected], got [$actual])"
    FAILURES=$((FAILURES + 1))
  fi
}

assert_ok() {
  local status="$1" msg="$2"
  if [ "$status" -ne 0 ]; then
    echo "FAIL: $msg (exit status $status)"
    FAILURES=$((FAILURES + 1))
  fi
}

assert_file_exists() {
  local path="$1" msg="$2"
  if [ ! -f "$path" ]; then
    echo "FAIL: $msg ($path does not exist)"
    FAILURES=$((FAILURES + 1))
  fi
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_DIR"' EXIT

cd "$FIXTURE_DIR"
git init -q
git config user.email "test@example.com"
git config user.name "Continuity Test"

# Seed .continuity/ content the way capture-trigger.sh's detached writer
# would, then commit it so the opt-out has something real to untrack.
bash "$REPO_ROOT/lib/write_memory.sh" "$FIXTURE_DIR" explicit-checkpoint >/dev/null 2>&1
git add .continuity 2>/dev/null
git commit -q -m "seed .continuity" 2>/dev/null

# Documented opt-out steps from docs/install.md, verbatim.
echo '.continuity/' >> .gitignore
git rm -r --cached .continuity/ >/dev/null 2>&1
git commit -q -m "Stop tracking .continuity/" 2>/dev/null

# Expected outcome: git no longer offers .continuity/ as trackable.
if git status --porcelain | grep -q '.continuity/'; then
  echo "FAIL: .continuity/ still appears in git status after opt-out"
  FAILURES=$((FAILURES + 1))
fi

# Expected outcome: Continuity still creates/reads/writes .continuity/ on
# disk exactly as before the opt-out — the opt-out is purely git's business.
bash "$REPO_ROOT/lib/write_memory.sh" "$FIXTURE_DIR" explicit-checkpoint >/dev/null 2>&1
assert_ok "$?" "write_memory.sh should still succeed after opting .continuity/ out of git"
assert_file_exists ".continuity/metadata.json" "metadata.json should still exist after opt-out"
assert_file_exists ".continuity/state.md" "state.md should still exist after opt-out"

if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: test_optout_persistence.sh"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) in test_optout_persistence.sh"
  exit 1
fi
