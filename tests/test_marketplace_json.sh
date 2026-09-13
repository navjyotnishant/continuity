#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Validates .claude-plugin/marketplace.json is parseable JSON and
#              carries the fields Claude Code's marketplace format requires.
#              Takes an optional manifest path (default: the repo's own), so a
#              deliberately broken manifest can be checked to fail.
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

# Valid JSON, the required marketplace fields, and a continuity plugin entry
# sourced from this repository (FR-015: this repo is the marketplace source).
python3 - "$manifest" <<'PY' || exit 1
import json, sys

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

for key in ("name", "owner", "plugins"):
    if not m.get(key):
        errors.append(f"missing top-level {key!r}")

owner = m.get("owner")
if not isinstance(owner, dict) or not owner.get("name"):
    errors.append("owner must be an object with a name")

plugins = m.get("plugins") or []
entry = next((p for p in plugins if isinstance(p, dict) and p.get("name") == "continuity"), None)
if entry is None:
    errors.append("no plugins entry named 'continuity'")
else:
    if entry.get("source") not in ("./", "."):
        errors.append(f"continuity source must be this repo root, got {entry.get('source')!r}")
    if not entry.get("description"):
        errors.append("continuity entry needs a description")

for e in errors:
    print(f"FAIL: {e}", file=sys.stderr)
sys.exit(1 if errors else 0)
PY

printf 'PASS: test_marketplace_json.sh (%s)\n' "$manifest"
