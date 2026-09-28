#!/usr/bin/env bash
# Covers a negative path the existing opt-out tests don't: docs/install.md
# step 2 is explicitly conditional ("If .continuity/ has already been
# committed in this repo, untrack the existing copy"). Every existing
# opt-out test seeds and commits .continuity/ first, so none of them
# exercise a reader who follows step 2 on a repo where .continuity/ was
# never committed. `git rm -r --cached` on an unindexed path is expected to
# fail there (nothing to untrack), which is exactly why the docs word step
# 2 as conditional rather than "always run this" — this test pins that
# down so a future doc edit that drops the qualifier gets caught.
set -u

FAILURES=0

assert_ok() {
  local status="$1" msg="$2"
  if [ "$status" -ne 0 ]; then
    echo "FAIL: $msg (exit status $status)"
    FAILURES=$((FAILURES + 1))
  fi
}

assert_fail() {
  local status="$1" msg="$2"
  if [ "$status" -eq 0 ]; then
    echo "FAIL: $msg (expected a non-zero exit status, got 0)"
    FAILURES=$((FAILURES + 1))
  fi
}

FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_DIR"' EXIT

cd "$FIXTURE_DIR"
git init -q
git config user.email "test@example.com"
git config user.name "Continuity Test"

# .continuity/ exists on disk but was never committed (step 1 only).
mkdir -p .continuity
echo "state" > .continuity/state.md
echo '.continuity/' >> .gitignore
assert_ok "$?" "step 1 alone (echo >> .gitignore) should succeed regardless of commit history"

# Running step 2 verbatim here must fail, since there is nothing tracked to
# untrack -- this is the case the docs' "if already committed" qualifier
# exists to warn about.
git rm -r --cached .continuity/ >/dev/null 2>&1
assert_fail "$?" "git rm -r --cached .continuity/ must fail on a repo where .continuity/ was never committed"

# Regardless of that failure, .continuity/ must still be absent from
# tracking and from disk it must be untouched -- the failed step-2 attempt
# must not have deleted anything on disk.
tracked="$(git ls-files .continuity)"
assert_ok "$([[ -z "$tracked" ]] && echo 0 || echo 1)" \
  ".continuity/ must remain untracked after a no-op/failed git rm --cached"

if [ ! -f .continuity/state.md ]; then
  echo "FAIL: .continuity/state.md must still exist on disk after the failed untrack attempt"
  FAILURES=$((FAILURES + 1))
fi

if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: test_optout_step2_conditional_on_prior_commit.sh"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) in test_optout_step2_conditional_on_prior_commit.sh"
  exit 1
fi
