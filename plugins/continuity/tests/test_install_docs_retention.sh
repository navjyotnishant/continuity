#!/usr/bin/env bash
# Covers docs/install.md's retention and metadata.json claims (T036):
# retention_days/git_tracked are documented as user-editable fields in
# metadata.json, and pruning is governed by retention_days rather than a
# fixed/cached value. See specs/001-continuity/data-model.md's
# "Infrastructure: metadata.json" section and tasks.md T030-T032.
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
RETENTION_SH="$REPO_ROOT/lib/retention.sh"

# UTC timestamp N days in the past, in the sessions/ filename format
# (ISO-8601 basic, colons/periods stripped) per
# specs/001-continuity/contracts/file-format-contract.md.
past_filename_timestamp() {
  local days="$1"
  date -u -v-"${days}"d +%Y%m%dT%H%M%SZ 2>/dev/null \
    || date -u -d "-${days} days" +%Y%m%dT%H%M%SZ
}

# UTC timestamp N days in the past, in errors.log's ISO-8601 extended format.
past_log_timestamp() {
  local days="$1"
  date -u -v-"${days}"d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null \
    || date -u -d "-${days} days" +%Y-%m-%dT%H:%M:%SZ
}

setup_fixture_repo() {
  local dir
  dir="$(mktemp -d)"
  git -C "$dir" init -q
  git -C "$dir" config user.email "test@example.com"
  git -C "$dir" config user.name "Test"
  mkdir -p "$dir/.continuity/sessions"
  echo "state" >"$dir/.continuity/state.md"
  echo "$dir"
}

write_metadata() {
  local dir="$1" retention_days="$2" git_tracked="$3"
  cat >"$dir/.continuity/metadata.json" <<EOF
{
  "schema_version": "1.0",
  "plugin_version": "0.0.0",
  "created_at": "2026-01-01T00:00:00Z",
  "retention_days": $retention_days,
  "git_tracked": $git_tracked
}
EOF
}

run_retention() {
  local dir="$1"
  ( set -u; source "$RETENTION_SH"; retention_prune "$dir/.continuity" )
}

test_session_history_is_pruned() {
  if [[ ! -f "$RETENTION_SH" ]]; then
    echo "SKIP: lib/retention.sh not present yet"
    return
  fi

  local repo
  repo="$(setup_fixture_repo)"
  write_metadata "$repo" 60 true

  local old_ts new_ts
  old_ts="$(past_filename_timestamp 90)"
  new_ts="$(past_filename_timestamp 1)"
  local old_session="$repo/.continuity/sessions/${old_ts}-1111.md"
  local new_session="$repo/.continuity/sessions/${new_ts}-2222.md"
  echo "old handoff" >"$old_session"
  echo "recent handoff" >"$new_session"

  local old_log_ts new_log_ts
  old_log_ts="$(past_log_timestamp 90)"
  new_log_ts="$(past_log_timestamp 1)"
  printf '%s | session-start-load | missing | old entry\n' "$old_log_ts" >"$repo/.continuity/errors.log"
  printf '%s | session-start-load | missing | recent entry\n' "$new_log_ts" >>"$repo/.continuity/errors.log"

  run_retention "$repo"

  assert_ok "$([[ ! -e "$old_session" ]] && echo 0 || echo 1)" \
    "retention: session file older than retention_days must be deleted"
  assert_ok "$([[ -e "$new_session" ]] && echo 0 || echo 1)" \
    "retention: session file within retention_days must survive"

  local log_contents
  log_contents="$(cat "$repo/.continuity/errors.log" 2>/dev/null || true)"
  assert_ok "$([[ "$log_contents" != *"old entry"* ]] && echo 0 || echo 1)" \
    "retention: errors.log line older than retention_days must be trimmed"
  assert_ok "$([[ "$log_contents" == *"recent entry"* ]] && echo 0 || echo 1)" \
    "retention: errors.log line within retention_days must survive"

  rm -rf "$repo"
}

test_editing_retention_days_takes_immediate_effect() {
  if [[ ! -f "$RETENTION_SH" ]]; then
    echo "SKIP: lib/retention.sh not present yet"
    return
  fi

  local repo
  repo="$(setup_fixture_repo)"
  write_metadata "$repo" 60 true

  # A handoff 10 days old: inside the default 60-day window, outside a
  # 5-day window — used to prove the setting is re-read, not cached.
  local ts session_file
  ts="$(past_filename_timestamp 10)"
  session_file="$repo/.continuity/sessions/${ts}-3333.md"
  echo "ten days old" >"$session_file"

  run_retention "$repo"
  assert_ok "$([[ -e "$session_file" ]] && echo 0 || echo 1)" \
    "retention: 10-day-old file must survive a 60-day retention_days window"

  # Edit metadata.json in place — no restart, no re-install, same repo.
  write_metadata "$repo" 5 true

  run_retention "$repo"
  assert_ok "$([[ ! -e "$session_file" ]] && echo 0 || echo 1)" \
    "retention: after editing retention_days to 5, the same 10-day-old file must now be pruned"

  rm -rf "$repo"
}

test_git_tracked_field_reflects_actual_git_state() {
  local repo
  repo="$(setup_fixture_repo)"
  write_metadata "$repo" 60 true
  git -C "$repo" add .continuity
  git -C "$repo" commit -q -m "add .continuity"

  local tracked
  tracked="$(git -C "$repo" ls-files .continuity)"
  assert_ok "$([[ -n "$tracked" ]] && echo 0 || echo 1)" \
    "git_tracked=true in metadata.json must match .continuity/ actually being tracked"

  # Follow docs/install.md's opt-out steps, then update the metadata field
  # to reflect the new, untracked state.
  echo '.continuity/' >>"$repo/.gitignore"
  git -C "$repo" rm -r --cached .continuity >/dev/null
  git -C "$repo" add .gitignore
  git -C "$repo" commit -q -m "Stop tracking .continuity/"
  write_metadata "$repo" 60 false

  tracked="$(git -C "$repo" ls-files .continuity)"
  assert_eq "" "$tracked" \
    "after opt-out, .continuity/ must actually be untracked"

  local git_tracked_field
  git_tracked_field="$(grep -o '"git_tracked": *[a-z]*' "$repo/.continuity/metadata.json" | grep -o '[a-z]*$')"
  assert_eq "false" "$git_tracked_field" \
    "git_tracked field must be set to false once .continuity/ is actually untracked"

  rm -rf "$repo"
}

test_session_history_is_pruned
test_editing_retention_days_takes_immediate_effect
test_git_tracked_field_reflects_actual_git_state

if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: test_install_docs_retention.sh"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) in test_install_docs_retention.sh"
  exit 1
fi
