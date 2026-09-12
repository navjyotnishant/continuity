#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Asserts test_structure.sh's own exit-code contract: 0 when all seven required directories exist, non-zero when any is missing.
set -u

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
failures=0

required_dirs=(.claude-plugin hooks commands lib templates tests docs)

sandbox="$(mktemp -d "${TMPDIR:-/tmp}/test_structure.XXXXXX")"
trap 'rm -rf "$sandbox"' EXIT

for dir in "${required_dirs[@]}"; do
  mkdir -p "$sandbox/$dir"
done
cp "$repo_root/tests/test_structure.sh" "$sandbox/tests/test_structure.sh"
chmod +x "$sandbox/tests/test_structure.sh"

if (cd "$sandbox" && ./tests/test_structure.sh >/dev/null 2>&1); then
  echo "ok   - test_structure.sh exits 0 when all required directories exist"
else
  echo "FAIL - test_structure.sh did not exit 0 with all required directories present"
  failures=$((failures + 1))
fi

missing_dir="${required_dirs[0]}"
rm -rf "${sandbox:?}/${missing_dir}"

if (cd "$sandbox" && ./tests/test_structure.sh >/dev/null 2>&1); then
  echo "FAIL - test_structure.sh exited 0 despite $missing_dir/ missing"
  failures=$((failures + 1))
else
  echo "ok   - test_structure.sh exits non-zero when $missing_dir/ is missing"
fi

exit "$failures"
