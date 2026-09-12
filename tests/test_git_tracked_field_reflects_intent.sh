#!/usr/bin/env bash
# Covers docs/install.md's metadata.json field docs (FR-020): git_tracked is
# "informational... a record of whether this project's .continuity/ is
# intended to be under version control." This is the one case from the QA
# spec (test_install_docs_retention.sh's
# test_git_tracked_field_reflects_actual_git_state) whose only existing
# coverage calls assert_ok/assert_eq without ever defining them in that
# file, so every assertion there silently no-ops ("command not found") and
# the test can never fail. This file re-covers the same scenario with real,
# self-contained assertions and no dependency on lib/ scripts that don't
# exist yet, so the case has at least one working check.
set -u

FAILURES=0

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
cat > .continuity/metadata.json <<'EOF'
{
  "schema_version": "1.0",
  "plugin_version": "0.0.0",
  "created_at": "2020-01-01T00:00:00Z",
  "retention_days": 60,
  "git_tracked": true
}
EOF
git add .continuity
git commit -q -m "seed .continuity with git_tracked: true"

# Opt out per docs/install.md, then hand-edit git_tracked to match reality,
# exactly as the docs describe ("update this field to match afterwards").
echo '.continuity/' >> .gitignore
git rm -r --cached .continuity/ >/dev/null
git add .gitignore
git commit -q -m "Stop tracking .continuity/"

sed -i.bak 's/"git_tracked": true/"git_tracked": false/' .continuity/metadata.json
rm -f .continuity/metadata.json.bak

# The field's claim (git_tracked: false) must match actual git state
# (.continuity/ genuinely untracked).
field_value="$(grep -o '"git_tracked": *[a-z]*' .continuity/metadata.json | grep -o '[a-z]*$')"
assert_eq "false" "$field_value" \
  "metadata.json's git_tracked field should read false after being hand-edited"

tracked="$(git ls-files .continuity)"
assert_eq "" "$tracked" \
  "git_tracked: false must match actual git state: .continuity/ must be untracked"

if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: test_git_tracked_field_reflects_intent.sh"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) in test_git_tracked_field_reflects_intent.sh"
  exit 1
fi
