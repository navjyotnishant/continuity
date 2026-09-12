#!/usr/bin/env bash
# Covers data-model.md's retention rule: lib/retention.sh prunes
# sessions/*.md and errors.log by age, but the four durable files
# (state.md, decisions.md, tasks.md, learnings.md) are never pruned,
# regardless of how old their mtime is.
set -u

FAILURES=0

assert_file_exists() {
  local path="$1" msg="$2"
  if [ ! -f "$path" ]; then
    echo "FAIL: $msg ($path is missing)"
    FAILURES=$((FAILURES + 1))
  fi
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_DIR"' EXIT

CONTINUITY_DIR="$FIXTURE_DIR/.continuity"
mkdir -p "$CONTINUITY_DIR/sessions"

cat > "$CONTINUITY_DIR/metadata.json" <<'EOF'
{
  "schema_version": "1.0",
  "plugin_version": "0.0.0",
  "created_at": "2020-01-01T00:00:00Z",
  "retention_days": 1,
  "git_tracked": true
}
EOF

echo "# State" > "$CONTINUITY_DIR/state.md"
echo "## Decision: old" > "$CONTINUITY_DIR/decisions.md"
echo "## Task: old" > "$CONTINUITY_DIR/tasks.md"
echo "## Learning: old" > "$CONTINUITY_DIR/learnings.md"

# Push every durable file's mtime well beyond retention_days, and also
# fabricate a stale sessions/ file that a pruner should legitimately delete
# — proving the pruner ran at all rather than durable files surviving
# because nothing was pruned.
OLD_STAMP="202001010000.00"
touch -t "$OLD_STAMP" \
  "$CONTINUITY_DIR/state.md" \
  "$CONTINUITY_DIR/decisions.md" \
  "$CONTINUITY_DIR/tasks.md" \
  "$CONTINUITY_DIR/learnings.md"

STALE_SESSION="$CONTINUITY_DIR/sessions/20200101T000000Z-1.md"
echo "captured_at: 2020-01-01T00:00:00Z | trigger: session-end" > "$STALE_SESSION"
touch -t "$OLD_STAMP" "$STALE_SESSION"

source "$REPO_ROOT/lib/retention.sh"
retention_prune "$CONTINUITY_DIR"

assert_file_exists "$CONTINUITY_DIR/state.md" "state.md must survive retention regardless of age"
assert_file_exists "$CONTINUITY_DIR/decisions.md" "decisions.md must survive retention regardless of age"
assert_file_exists "$CONTINUITY_DIR/tasks.md" "tasks.md must survive retention regardless of age"
assert_file_exists "$CONTINUITY_DIR/learnings.md" "learnings.md must survive retention regardless of age"

if [ -f "$STALE_SESSION" ]; then
  echo "FAIL: stale sessions/ file older than retention_days should have been pruned"
  FAILURES=$((FAILURES + 1))
fi

if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: test_retention_durable_safety.sh"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) in test_retention_durable_safety.sh"
  exit 1
fi
