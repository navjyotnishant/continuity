#!/usr/bin/env bash
# Covers docs/install.md's secret-scan disclaimer (T036, plan.md's Risks):
# the docs must state plainly that lib/secret_scan.sh can have false
# negatives and is a mitigation, not a guarantee — so nobody reads the scan
# as a substitute for their own judgment about what gets persisted.
set -u

FAILURES=0

assert_contains() {
  local file="$1" pattern="$2" msg="$3"
  if ! grep -qi -- "$pattern" "$file" 2>/dev/null; then
    echo "FAIL: $msg (pattern [$pattern] not found in $file)"
    FAILURES=$((FAILURES + 1))
  fi
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_DOC="$REPO_ROOT/docs/install.md"

if [[ ! -f "$INSTALL_DOC" ]]; then
  echo "FAIL: docs/install.md does not exist"
  FAILURES=$((FAILURES + 1))
else
  assert_contains "$INSTALL_DOC" "false negative" \
    "docs/install.md must state the scan can have false negatives"
  assert_contains "$INSTALL_DOC" "not.*substitute.*judgment" \
    "docs/install.md must state the scan is not a substitute for the user's own judgment"
  assert_contains "$INSTALL_DOC" "mitigation" \
    "docs/install.md must frame secret scanning as a mitigation, not a guarantee"
fi

if [ "$FAILURES" -eq 0 ]; then
  echo "PASS: test_secret_scan_limitation_documented.sh"
  exit 0
else
  echo "FAILED: $FAILURES assertion(s) in test_secret_scan_limitation_documented.sh"
  exit 1
fi
