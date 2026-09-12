#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Asserts the plugin directory tree from plan.md exists at the repo root.
set -u

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
failures=0

for dir in .claude-plugin hooks commands lib templates tests docs; do
  if [ -d "$repo_root/$dir" ]; then
    echo "ok   - $dir/ exists"
  else
    echo "FAIL - $dir/ is missing"
    failures=$((failures + 1))
  fi
done

exit "$failures"
