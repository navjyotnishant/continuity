#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-27
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

for dir in .claude-plugin hooks commands lib templates tests docs; do
  if [ -r "$repo_root/$dir" ] && [ -w "$repo_root/$dir" ]; then
    echo "ok   - $dir/ is readable and writable"
  else
    echo "FAIL - $dir/ is not readable/writable"
    failures=$((failures + 1))
  fi
done


if [ -x "$repo_root/tests/test_structure.sh" ]; then
  echo "ok   - tests/test_structure.sh is executable"
else
  echo "FAIL - tests/test_structure.sh is not executable"
  failures=$((failures + 1))
fi

exit "$failures"
