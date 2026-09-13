#!/usr/bin/env bash
# Covers data-model.md's metadata.json infrastructure entity and
# docs/install.md's documented defaults: on first creation, metadata.json
# must exist with retention_days: 60 and git_tracked: true.
set -u

FAILURES=0

assert_ok() {
  local status="$1" msg="$2"
  if [ "$status" -ne 0 ]; then
    echo "FAIL: $msg (exit status $status)"
    FAILURES=$((FAILURES + 1))
  fi
}

assert_contains() {
  local file="$1" pattern="$2" msg="$3"
  if ! grep -q -- "$pattern" "$file" 2>/dev/null; then
    echo "FAIL: $msg (pattern [$pattern] not found in $file)"
    FAILURES=$((FAILURES + 1))
  fi
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_DIR"' EXIT

# No .continuity/ present yet: first trigger must auto-create and seed it
# (T029), producing metadata.json with the documented defaults.
bash "$REPO_ROOT/lib/write_memory.sh" "$FIXTURE_DIR" explicit-checkpoint >/dev/null 2>&1
assert_ok "$?" "write_memory.sh should succeed on first run against a project with no .continuity/"

METADATA="$FIXTURE_DIR/.continuity/metadata.json"
if [ ! -f "$METADATA" ]; then
  echo "FAIL: .continuity/metadata.json was not created on first run"
  FAILURES=$((FAILURES + 1))
else
  assert_contains "$METADATA" '"retention_days"[[:space:]]*:[[:space:]]*60' \
    "metadata.json should default retention_days to 60"
  assert_contains "$METADATA" '"git_tracked"[[:space:]]*:[[:space:]]*true' \
    "metadata.json should default git_tracked to true"
fi

if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: test_metadata_defaults.sh"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) in test_metadata_defaults.sh"
  exit 1
fi
