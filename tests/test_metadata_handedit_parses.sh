#!/usr/bin/env bash
# Covers docs/install.md's "Configuring retention and tracking in
# metadata.json" section (T036): retention_days/git_tracked are documented
# as fields a user can hand-edit directly, with write_memory.sh/retention.sh
# re-reading the file on every run. This asserts a hand-written edit (not
# one produced by Continuity itself, so unconventional-but-valid JSON
# whitespace/field order) is parsed and used without error.
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
WRITE_MEMORY_SH="$REPO_ROOT/lib/write_memory.sh"
RETENTION_SH="$REPO_ROOT/lib/retention.sh"

FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_DIR"' EXIT

git -C "$FIXTURE_DIR" init -q
git -C "$FIXTURE_DIR" config user.email "test@example.com"
git -C "$FIXTURE_DIR" config user.name "Test"
mkdir -p "$FIXTURE_DIR/.continuity/sessions"
echo "state" >"$FIXTURE_DIR/.continuity/state.md"

# A hand-written edit: unusual spacing/field order/quoting a human would
# actually type, not the canonical output write_memory.sh itself produces.
cat >"$FIXTURE_DIR/.continuity/metadata.json" <<'EOF'
{
    "git_tracked":false,
  "retention_days" : 14,
    "schema_version": "1.0",
        "plugin_version": "0.0.0",
    "created_at": "2026-01-01T00:00:00Z"
}
EOF

if [[ ! -x "$WRITE_MEMORY_SH" ]]; then
  echo "SKIP: lib/write_memory.sh not present yet"
else
  bash "$WRITE_MEMORY_SH" "$FIXTURE_DIR" explicit-checkpoint >/dev/null 2>&1
  assert_ok "$?" "write_memory.sh must succeed against a hand-edited (but valid) metadata.json"

  retention_field="$(grep -o '"retention_days"[[:space:]]*:[[:space:]]*[0-9]*' \
    "$FIXTURE_DIR/.continuity/metadata.json" | grep -o '[0-9]*$')"
  assert_eq "14" "$retention_field" \
    "hand-edited retention_days=14 must survive a write_memory.sh run, not get reset to a default"
fi

if [[ ! -f "$RETENTION_SH" ]]; then
  echo "SKIP: lib/retention.sh not present yet"
else
  # A session file 30 days old: outside the hand-edited 14-day window, so
  # retention_prune must have actually read the hand-written value.
  old_ts="$(date -u -v-30d +%Y%m%dT%H%M%SZ 2>/dev/null || date -u -d "-30 days" +%Y%m%dT%H%M%SZ)"
  old_session="$FIXTURE_DIR/.continuity/sessions/${old_ts}-9999.md"
  echo "old handoff" >"$old_session"

  ( set -u; source "$RETENTION_SH"; retention_prune "$FIXTURE_DIR/.continuity" )
  assert_ok "$?" "retention_prune must run without error against the hand-edited metadata.json"
  assert_ok "$([[ ! -e "$old_session" ]] && echo 0 || echo 1)" \
    "retention_prune must honor the hand-edited retention_days=14, pruning a 30-day-old file"
fi

if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: test_metadata_handedit_parses.sh"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) in test_metadata_handedit_parses.sh"
  exit 1
fi
