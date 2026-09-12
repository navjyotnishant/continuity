#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Validates .claude-plugin/marketplace.json's continuity plugin
#              entry - required fields, source, description, category, and
#              field types (T034 cases 13-18). Takes an optional manifest
#              path (default: the repo's own), so a deliberately broken
#              manifest can be checked to fail.
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="${1:-$repo_root/.claude-plugin/marketplace.json}"

if [ ! -r "$manifest" ]; then
  printf 'FAIL: cannot read %s\n' "$manifest" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  printf 'SKIP: python3 not available for JSON validation\n'
  exit 0
fi

python3 - "$manifest" <<'PY' || exit 1
import json, re, sys

# No enum is published for this field in Claude Code's marketplace schema as
# of this writing (see specs/001-continuity/tasks.md T034), so "valid" is
# checked structurally: a non-empty lowercase-kebab slug, not free text.
CATEGORY_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")

errors = []
try:
    with open(sys.argv[1]) as fh:
        m = json.load(fh)
except (OSError, ValueError) as exc:
    print(f"FAIL: not valid JSON: {exc}", file=sys.stderr)
    sys.exit(1)

if not isinstance(m, dict):
    print("FAIL: top level must be a JSON object", file=sys.stderr)
    sys.exit(1)

plugins = m.get("plugins")
if not isinstance(plugins, list):
    print("FAIL: plugins must be an array; cannot check continuity entry", file=sys.stderr)
    sys.exit(1)

# Case 13: plugins array contains an entry with name="continuity"
continuity_entries = [p for p in plugins if isinstance(p, dict) and p.get("name") == "continuity"]
if len(continuity_entries) != 1:
    errors.append(f"case 13: expected exactly one plugins entry with name='continuity', found {len(continuity_entries)}")

entry = continuity_entries[0] if continuity_entries else None

if entry is not None:
    # Case 14: required fields present
    for field in ("name", "description", "source", "category"):
        if field not in entry:
            errors.append(f"case 14: continuity entry missing required field {field!r}")

    # Case 15: source is "./" (repo root, not elsewhere)
    source = entry.get("source")
    if source != "./":
        errors.append(f"case 15: continuity entry source must be './', got {source!r}")

    # Case 16: description is non-empty and meaningful (more than a token or two)
    description = entry.get("description")
    if not isinstance(description, str) or not description.strip():
        errors.append("case 16: continuity entry description must be a non-empty string")
    elif len(description.strip().split()) < 3:
        errors.append(f"case 16: continuity entry description does not look meaningful, got {description!r}")

    # Case 17: category is a valid marketplace category (non-empty kebab-case slug)
    category = entry.get("category")
    if not isinstance(category, str) or not CATEGORY_RE.match(category):
        errors.append(f"case 17: continuity entry category {category!r} is not a valid marketplace category slug")

    # Case 18: all field values are of the correct type
    if "name" in entry and not isinstance(entry.get("name"), str):
        errors.append(f"case 18: continuity entry 'name' must be a string, got {type(entry.get('name')).__name__}")
    if "description" in entry and not isinstance(entry.get("description"), str):
        errors.append(f"case 18: continuity entry 'description' must be a string, got {type(entry.get('description')).__name__}")
    if "source" in entry and not isinstance(entry.get("source"), str):
        errors.append(f"case 18: continuity entry 'source' must be a string, got {type(entry.get('source')).__name__}")
    if "category" in entry and not isinstance(entry.get("category"), str):
        errors.append(f"case 18: continuity entry 'category' must be a string, got {type(entry.get('category')).__name__}")

for e in errors:
    print(f"FAIL: {e}", file=sys.stderr)
sys.exit(1 if errors else 0)
PY

printf 'PASS: test_marketplace_json_continuity_entry.sh (%s)\n' "$manifest"
