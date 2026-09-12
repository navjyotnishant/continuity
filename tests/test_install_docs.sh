#!/usr/bin/env bash
# Covers docs/install.md's opt-out steps (Q1/FR-020, quickstart Scenario 5):
# adding .continuity/ to .gitignore untracks it correctly on a fresh and an
# already-committed repo, and new files stay untracked afterward.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

setup_fixture_repo() {
  local dir
  dir="$(mktemp -d)"
  git -C "$dir" init -q
  git -C "$dir" config user.email "test@example.com"
  git -C "$dir" config user.name "Test"
  echo "$dir"
}

test_fresh_repo_opt_out_untracks() {
  local repo
  repo="$(setup_fixture_repo)"
  mkdir -p "$repo/.continuity"
  echo "state" >"$repo/.continuity/state.md"

  echo '.continuity/' >>"$repo/.gitignore"

  local status
  status="$(git -C "$repo" status --porcelain)"
  assert_ok "$([[ "$status" != *".continuity"* ]] && echo 0 || echo 1)" \
    "fresh repo: .continuity/ must not appear in git status after gitignore"

  git -C "$repo" add -A
  local staged
  staged="$(git -C "$repo" diff --cached --name-only)"
  assert_ok "$([[ "$staged" != *".continuity"* ]] && echo 0 || echo 1)" \
    "fresh repo: .continuity/ must not be staged after git add -A"

  rm -rf "$repo"
}

test_existing_commits_untrack_correctly() {
  local repo
  repo="$(setup_fixture_repo)"
  mkdir -p "$repo/.continuity"
  echo "state" >"$repo/.continuity/state.md"
  git -C "$repo" add .continuity
  git -C "$repo" commit -q -m "add .continuity"

  echo '.continuity/' >>"$repo/.gitignore"
  git -C "$repo" rm -r --cached .continuity >/dev/null
  git -C "$repo" add .gitignore
  git -C "$repo" commit -q -m "Stop tracking .continuity/"

  local tracked
  tracked="$(git -C "$repo" ls-files .continuity)"
  assert_eq "" "$tracked" \
    "existing commits: .continuity/ must be removed from the index"

  assert_ok "$([[ -f "$repo/.continuity/state.md" ]] && echo 0 || echo 1)" \
    "existing commits: .continuity/state.md must still exist on disk"

  rm -rf "$repo"
}

test_new_files_after_opt_out_stay_untracked() {
  local repo
  repo="$(setup_fixture_repo)"
  mkdir -p "$repo/.continuity/sessions"
  echo "state" >"$repo/.continuity/state.md"
  git -C "$repo" add .continuity
  git -C "$repo" commit -q -m "add .continuity"

  echo '.continuity/' >>"$repo/.gitignore"
  git -C "$repo" rm -r --cached .continuity >/dev/null
  git -C "$repo" add .gitignore
  git -C "$repo" commit -q -m "Stop tracking .continuity/"

  # Simulate Continuity writing a new session handoff file after opt-out.
  if [[ -x "$REPO_ROOT/lib/write_memory.sh" ]]; then
    "$REPO_ROOT/lib/write_memory.sh" "$repo" explicit-checkpoint >/dev/null 2>&1
  else
    echo "session" >"$repo/.continuity/sessions/$(date +%s)-$$.md"
  fi

  local status
  status="$(git -C "$repo" status --porcelain)"
  assert_ok "$([[ "$status" != *".continuity"* ]] && echo 0 || echo 1)" \
    "post opt-out: new .continuity/ file must not appear in git status"

  git -C "$repo" add -A
  local staged
  staged="$(git -C "$repo" diff --cached --name-only)"
  assert_ok "$([[ "$staged" != *".continuity"* ]] && echo 0 || echo 1)" \
    "post opt-out: git add . must not stage the new .continuity/ file"

  rm -rf "$repo"
}

test_fresh_repo_opt_out_untracks
test_existing_commits_untrack_correctly
test_new_files_after_opt_out_stay_untracked
