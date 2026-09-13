#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Asserts the seven plugin directories are real dirs, empty-or-gitkeep-only, and no extras exist.
set -u

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
failures=0

expected_dirs=(.claude-plugin hooks commands lib templates tests docs)

for dir in "${expected_dirs[@]}"; do
  path="$repo_root/$dir"
  if [ -L "$path" ]; then
    echo "FAIL - $dir is a symlink, not a directory"
    failures=$((failures + 1))
  elif [ -d "$path" ]; then
    echo "ok   - $dir/ is a directory"
  elif [ -e "$path" ]; then
    echo "FAIL - $dir exists but is not a directory"
    failures=$((failures + 1))
  else
    echo "FAIL - $dir is missing"
    failures=$((failures + 1))
  fi
done

# tests/ and docs/ are excluded here: tests/ must hold the test scripts
# this ticket itself requires, and docs/ pre-existed T001 with real content
# (docs/intent/continuity.md) that T001's own commit explicitly left alone.
# The "empty or .gitkeep only" criterion applies to the five dirs T001
# created from scratch.
empty_check_dirs=(.claude-plugin hooks commands lib templates)

for dir in "${empty_check_dirs[@]}"; do
  path="$repo_root/$dir"
  [ -d "$path" ] || continue
  unexpected=$(find "$path" -mindepth 1 -not -name ".gitkeep")
  if [ -z "$unexpected" ]; then
    echo "ok   - $dir/ is empty or contains only .gitkeep"
  else
    echo "FAIL - $dir/ contains unexpected entries:"
    echo "$unexpected" | sed 's/^/       /'
    failures=$((failures + 1))
  fi
done

# plan.md names exactly these seven for the plugin tree; a typo'd or
# duplicated sibling (e.g. "hook" alongside "hooks") would silently break
# Claude Code's path-based discovery of the manifest/hooks/commands dirs.
# Plain array of "variant" names, not a map keyed by stem: associative
# arrays need bash 4+, but macOS ships bash 3.2 and this plugin targets
# bash portability, so this stays a flat list.
near_miss_found=0
near_miss_variants=(.claude_plugin claudeplugin hook Hooks command Commands libs Lib template Templates test Tests doc Docs)
for variant in "${near_miss_variants[@]}"; do
  # [ -e ] is case-insensitive on macOS's default APFS, so "Hooks" would
  # false-positive-match the real "hooks" dir; find -name compares the
  # literal directory-entry name instead.
  if [ -n "$(find "$repo_root" -maxdepth 1 -name "$variant")" ]; then
    echo "FAIL - unintended near-duplicate of a plugin dir found: $variant"
    failures=$((failures + 1))
    near_miss_found=1
  fi
done
[ "$near_miss_found" -eq 0 ] && echo "ok   - no unintended near-duplicate plugin directories found"

exit "$failures"
