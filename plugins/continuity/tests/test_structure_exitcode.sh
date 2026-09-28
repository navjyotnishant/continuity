#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Asserts test_structure.sh's own exit-code contract: 0 when all
#              required plugin directories plus the project-root docs/ exist,
#              non-zero when any is missing.
set -u

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
failures=0

required_dirs=(.claude-plugin hooks commands lib templates tests)

sandbox="$(mktemp -d "${TMPDIR:-/tmp}/test_structure.XXXXXX")"
trap 'rm -rf "$sandbox"' EXIT

# Mirror the real layout: a project root with docs/, and the plugin two
# levels below it at plugins/continuity/, so test_structure.sh's own
# PROJECT_ROOT resolution (repo_root/../..) lands on this sandbox's root.
plugin_dir="$sandbox/plugins/continuity"
for dir in "${required_dirs[@]}"; do
  mkdir -p "$plugin_dir/$dir"
done
mkdir -p "$sandbox/docs"
cp "$repo_root/tests/test_structure.sh" "$plugin_dir/tests/test_structure.sh"
chmod +x "$plugin_dir/tests/test_structure.sh"

if (cd "$plugin_dir" && ./tests/test_structure.sh >/dev/null 2>&1); then
  echo "ok   - test_structure.sh exits 0 when all required directories exist"
else
  echo "FAIL - test_structure.sh did not exit 0 with all required directories present"
  failures=$((failures + 1))
fi

missing_dir="${required_dirs[0]}"
rm -rf "${plugin_dir:?}/${missing_dir}"

if (cd "$plugin_dir" && ./tests/test_structure.sh >/dev/null 2>&1); then
  echo "FAIL - test_structure.sh exited 0 despite $missing_dir/ missing"
  failures=$((failures + 1))
else
  echo "ok   - test_structure.sh exits non-zero when $missing_dir/ is missing"
fi

# Restore, then remove the project-root docs/ instead, to prove the new
# PROJECT_ROOT/docs check is what fails this time.
mkdir -p "$plugin_dir/$missing_dir"
rm -rf "${sandbox:?}/docs"

if (cd "$plugin_dir" && ./tests/test_structure.sh >/dev/null 2>&1); then
  echo "FAIL - test_structure.sh exited 0 despite the project root's docs/ missing"
  failures=$((failures + 1))
else
  echo "ok   - test_structure.sh exits non-zero when the project root's docs/ is missing"
fi

exit "$failures"
