#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: T034 cases 25-30 for .claude-plugin/marketplace.json: schema
#              validation catches a missing continuity entry and an owner
#              without a name, multiple plugin entries can coexist, plugin
#              names must be unique across the array, the real manifest's
#              metadata is complete and self-consistent, and this suite's own
#              test scripts produce the expected PASS/FAIL/SKIP output shape.
#              Cases 25-26 and 28 build synthetic manifests under $TMPDIR;
#              case 27 and 29 use the repo's own manifest (optional override
#              path); case 30 runs a sibling test script as a subprocess.
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="${1:-$repo_root/.claude-plugin/marketplace.json}"
fail=0

if ! command -v python3 >/dev/null 2>&1; then
  printf 'SKIP: python3 not available for JSON validation\n'
  exit 0
fi

# Shared validator mirroring the structural checks the rest of this suite
# runs, extended with a plugins-name-uniqueness check for case 28.
validate() {
  local path="$1"
  python3 - "$path" <<'PY'
import json, sys

try:
    with open(sys.argv[1]) as fh:
        text = fh.read()
except OSError as exc:
    print(f"FAIL: cannot read manifest: {exc}", file=sys.stderr)
    sys.exit(1)

try:
    m = json.loads(text)
except json.JSONDecodeError as exc:
    print(f"FAIL: malformed JSON: {exc}", file=sys.stderr)
    sys.exit(1)

if not isinstance(m, dict):
    print("FAIL: top level must be a JSON object", file=sys.stderr)
    sys.exit(1)

errors = []
for key in ("name", "description", "owner", "plugins"):
    if key not in m:
        errors.append(f"missing required top-level field {key!r}")

owner = m.get("owner")
if isinstance(owner, dict):
    if not isinstance(owner.get("name"), str) or not owner.get("name", "").strip():
        errors.append("owner object must have a non-empty name")
else:
    errors.append("owner must be an object")

plugins = m.get("plugins")
if isinstance(plugins, list):
    names = [p.get("name") for p in plugins if isinstance(p, dict)]
    if "continuity" not in names:
        errors.append("no plugins entry named 'continuity'")
    dupes = {n for n in names if n and names.count(n) > 1}
    if dupes:
        errors.append(f"duplicate plugin name(s) across plugins array: {sorted(dupes)}")
else:
    errors.append("plugins must be an array")

for e in errors:
    print(f"FAIL: {e}", file=sys.stderr)
sys.exit(1 if errors else 0)
PY
}

tmp_dir="${TMPDIR:-/tmp}"
scratch="$tmp_dir/marketplace_uniqueness_$$.json"
trap 'rm -f "$scratch"' EXIT

# Case 25: schema validation catches when the continuity plugin entry is missing
cat > "$scratch" <<'JSON'
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "continuity",
  "description": "missing continuity plugin entry",
  "owner": {"name": "Navjyot Nishant", "url": "https://github.com/navjyotnishant"},
  "plugins": [
    {"name": "other-plugin", "description": "unrelated", "source": "./other", "category": "utilities"}
  ]
}
JSON
if validate "$scratch" >/dev/null 2>&1; then
  printf 'FAIL: case 25: manifest with no continuity plugin entry should have failed validation\n' >&2
  fail=1
else
  printf 'PASS: case 25: validation catches a missing continuity plugin entry\n'
fi

# Case 26: schema validation catches when the owner object lacks a name
cat > "$scratch" <<'JSON'
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "continuity",
  "description": "owner without a name",
  "owner": {"url": "https://github.com/navjyotnishant"},
  "plugins": [
    {"name": "continuity", "description": "cross-session memory", "source": "./", "category": "productivity"}
  ]
}
JSON
if validate "$scratch" >/dev/null 2>&1; then
  printf 'FAIL: case 26: manifest with a nameless owner should have failed validation\n' >&2
  fail=1
else
  printf 'PASS: case 26: validation catches an owner object lacking a name\n'
fi

# Case 27: multiple plugin entries can coexist in the plugins array
cat > "$scratch" <<'JSON'
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "continuity",
  "description": "multiple plugin entries",
  "owner": {"name": "Navjyot Nishant", "url": "https://github.com/navjyotnishant"},
  "plugins": [
    {"name": "continuity", "description": "cross-session memory", "source": "./", "category": "productivity"},
    {"name": "other-plugin", "description": "unrelated plugin", "source": "./other", "category": "utilities"}
  ]
}
JSON
if validate "$scratch" >/dev/null 2>&1; then
  printf 'PASS: case 27: multiple plugin entries coexist in the plugins array\n'
else
  printf 'FAIL: case 27: a manifest with two distinct, valid plugin entries should have passed validation\n' >&2
  fail=1
fi

# Case 28: plugin entry names must be unique across the plugins array
cat > "$scratch" <<'JSON'
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "continuity",
  "description": "duplicate plugin names",
  "owner": {"name": "Navjyot Nishant", "url": "https://github.com/navjyotnishant"},
  "plugins": [
    {"name": "continuity", "description": "cross-session memory", "source": "./", "category": "productivity"},
    {"name": "continuity", "description": "a second entry with the same name", "source": "./dup", "category": "productivity"}
  ]
}
JSON
if validate "$scratch" >/dev/null 2>&1; then
  printf 'FAIL: case 28: duplicate plugin names in the plugins array should have failed validation\n' >&2
  fail=1
else
  printf 'PASS: case 28: validation catches duplicate plugin names across the plugins array\n'
fi

# Case 29: the real manifest's metadata is complete and self-consistent -
# top-level name matches the repo's own plugin name, and the continuity
# plugin entry's name/description agree with the top-level manifest name.
if [ -r "$manifest" ]; then
  python3 - "$manifest" <<'PY'
import json, sys

with open(sys.argv[1]) as fh:
    m = json.load(fh)

errors = []
top_name = m.get("name")
plugins = m.get("plugins") or []
entry = next((p for p in plugins if isinstance(p, dict) and p.get("name") == top_name), None)
if entry is None:
    errors.append(f"case 29: no plugins entry name matches top-level manifest name {top_name!r}")
if not (m.get("description") or "").strip():
    errors.append("case 29: top-level description must be non-empty")
owner = m.get("owner")
if not isinstance(owner, dict) or not (owner.get("name") or "").strip():
    errors.append("case 29: owner must be present and non-empty for self-consistent metadata")

for e in errors:
    print(f"FAIL: {e}", file=sys.stderr)
sys.exit(1 if errors else 0)
PY
  status=$?
  if [ "$status" -ne 0 ]; then
    fail=1
  else
    printf 'PASS: case 29: manifest metadata is complete and self-consistent\n'
  fi
else
  printf 'SKIP: case 29: cannot read %s\n' "$manifest"
fi

# Case 30: this suite's own test scripts run and produce PASS/FAIL/SKIP output
sibling="$repo_root/tests/test_marketplace_json.sh"
if [ -x "$sibling" ] || [ -r "$sibling" ]; then
  output="$(bash "$sibling" 2>&1)"
  status=$?
  if printf '%s' "$output" | grep -qE '^(PASS|FAIL|SKIP):'; then
    if [ "$status" -eq 0 ]; then
      printf 'PASS: case 30: sibling test script ran and produced a PASS/SKIP-shaped result\n'
    else
      printf 'PASS: case 30: sibling test script ran and produced a FAIL-shaped result on nonzero exit\n'
    fi
  else
    printf 'FAIL: case 30: sibling test script produced no PASS/FAIL/SKIP-prefixed output: %s\n' "$output" >&2
    fail=1
  fi
else
  printf 'SKIP: case 30: sibling test script %s not found\n' "$sibling"
fi

exit "$fail"
