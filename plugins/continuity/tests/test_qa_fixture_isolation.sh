#!/usr/bin/env bash
# Covers T036's own QA claim ("following the documented opt-out steps
# against a fixture repo"): every install.md test case runs against a
# temporary fixture repo, never the actual working repo, so QA-ing the
# opt-out/metadata docs leaves this repo's own .continuity/ untouched.
set -u

FAILURES=0

assert_ok() {
  local status="$1" msg="$2"
  if [ "$status" -ne 0 ]; then
    echo "FAIL: $msg (exit status $status)"
    FAILURES=$((FAILURES + 1))
  fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WRITE_MEMORY_SH="$REPO_ROOT/lib/write_memory.sh"
REAL_CONTINUITY="$REPO_ROOT/.continuity"

# Snapshot the working repo's state before running anything, so any drift
# caused by the test itself is caught rather than assumed away.
pre_existed=0
[[ -e "$REAL_CONTINUITY" ]] && pre_existed=1
pre_listing=""
[[ $pre_existed -eq 1 ]] && pre_listing="$(find "$REAL_CONTINUITY" -type f | sort)"
pre_git_status="$(git -C "$REPO_ROOT" status --porcelain -- .continuity 2>/dev/null)"

# Run the same kind of operations the other install.md cases exercise
# (write, opt-out, hand-edit) against an isolated fixture repo only.
FIXTURE_DIR="$(mktemp -d)"
trap 'rm -rf "$FIXTURE_DIR"' EXIT

git -C "$FIXTURE_DIR" init -q
git -C "$FIXTURE_DIR" config user.email "test@example.com"
git -C "$FIXTURE_DIR" config user.name "Test"

if [[ ! -x "$WRITE_MEMORY_SH" ]]; then
  echo "SKIP: lib/write_memory.sh not present yet — isolation still verified against the fixture-only setup above"
else
  bash "$WRITE_MEMORY_SH" "$FIXTURE_DIR" explicit-checkpoint >/dev/null 2>&1
fi
echo '.continuity/' >>"$FIXTURE_DIR/.gitignore"
if [[ -d "$FIXTURE_DIR/.continuity" ]]; then
  git -C "$FIXTURE_DIR" add .continuity >/dev/null 2>&1
  git -C "$FIXTURE_DIR" commit -q -m "seed .continuity" >/dev/null 2>&1
  git -C "$FIXTURE_DIR" rm -r --cached .continuity >/dev/null 2>&1
  git -C "$FIXTURE_DIR" commit -q -m "Stop tracking .continuity/" >/dev/null 2>&1
fi

# The fixture must actually be a separate directory from the working repo.
assert_ok "$([[ "$FIXTURE_DIR" != "$REPO_ROOT" ]] && echo 0 || echo 1)" \
  "fixture repo must not be the working repo itself"

# The working repo's .continuity/ must be exactly as it was before this
# test ran: no new files, no removed files, no new git status entries.
post_existed=0
[[ -e "$REAL_CONTINUITY" ]] && post_existed=1
assert_ok "$([ "$pre_existed" -eq "$post_existed" ] && echo 0 || echo 1)" \
  "working repo's .continuity/ existence must be unchanged by QA-ing install.md"

if [[ $pre_existed -eq 1 ]]; then
  post_listing="$(find "$REAL_CONTINUITY" -type f | sort)"
  assert_ok "$([ "$pre_listing" = "$post_listing" ] && echo 0 || echo 1)" \
    "working repo's .continuity/ file listing must be unchanged by QA-ing install.md"
fi

post_git_status="$(git -C "$REPO_ROOT" status --porcelain -- .continuity 2>/dev/null)"
assert_ok "$([ "$pre_git_status" = "$post_git_status" ] && echo 0 || echo 1)" \
  "working repo's git status for .continuity/ must be unchanged by QA-ing install.md"

if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: test_qa_fixture_isolation.sh"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) in test_qa_fixture_isolation.sh"
  exit 1
fi
