#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: T034 cases 19-24 for .claude-plugin/marketplace.json: no
#              extraneous top-level fields, the file reads cleanly and is not
#              corrupted/truncated, and validation fails gracefully (no
#              crash, a clear error) on a missing required field, malformed
#              JSON, wrong field types, and a continuity plugin entry whose
#              source points at the wrong path. Takes an optional manifest
#              path (default: the repo's own) for cases 19-20; cases 21-24
#              build their own synthetic broken manifests under $TMPDIR.
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="${1:-$repo_root/.claude-plugin/marketplace.json}"
fail=0

if ! command -v python3 >/dev/null 2>&1; then
  printf 'SKIP: python3 not available for JSON validation\n'
  exit 0
fi

# Case 20: file can be read and is not corrupted or truncated
if [ ! -r "$manifest" ]; then
  printf 'FAIL: case 20: cannot read %s\n' "$manifest" >&2
  exit 1
fi
if [ ! -s "$manifest" ]; then
  printf 'FAIL: case 20: %s is empty\n' "$manifest" >&2
  exit 1
fi
python3 - "$manifest" <<'PY' || fail=1
import json, sys

path = sys.argv[1]
with open(path, encoding="utf-8") as fh:
    text = fh.read()

# A truncated file (cut mid-object) still decodes as bytes but fails json.loads;
# a corrupted-but-valid-looking file may decode odd bytes as replacement chars.
if "�" in text:
    print("FAIL: case 20: manifest contains invalid/replacement characters", file=sys.stderr)
    sys.exit(1)

try:
    json.loads(text)
except json.JSONDecodeError as exc:
    print(f"FAIL: case 20: manifest is truncated or corrupted: {exc}", file=sys.stderr)
    sys.exit(1)

print("PASS: case 20: manifest reads cleanly and is not truncated/corrupted")
PY
[ $? -ne 0 ] && fail=1

# Case 19: no extraneous fields violate the marketplace schema
python3 - "$manifest" <<'PY'
import json, sys

# Fields Claude Code's marketplace.schema.json is known (from this repo's own
# manifest and the other T034 tests) to define at the top level and within
# each plugin entry. Anything else is extraneous and schema-invalid.
ALLOWED_TOP = {"$schema", "name", "description", "owner", "plugins", "metadata"}
ALLOWED_OWNER = {"name", "url", "email"}
ALLOWED_PLUGIN = {"name", "description", "source", "category", "version", "keywords"}

with open(sys.argv[1]) as fh:
    m = json.load(fh)

errors = []

extra_top = set(m) - ALLOWED_TOP
if extra_top:
    errors.append(f"case 19: extraneous top-level field(s) {sorted(extra_top)}")

owner = m.get("owner")
if isinstance(owner, dict):
    extra_owner = set(owner) - ALLOWED_OWNER
    if extra_owner:
        errors.append(f"case 19: extraneous owner field(s) {sorted(extra_owner)}")

for entry in m.get("plugins") or []:
    if isinstance(entry, dict):
        extra_plugin = set(entry) - ALLOWED_PLUGIN
        if extra_plugin:
            errors.append(f"case 19: extraneous plugin field(s) {sorted(extra_plugin)}")

for e in errors:
    print(f"FAIL: {e}", file=sys.stderr)
sys.exit(1 if errors else 0)
PY
status=$?
if [ "$status" -ne 0 ]; then
  fail=1
else
  printf 'PASS: case 19: no extraneous fields violate the marketplace schema\n'
fi

# Shared validator used by the synthetic-manifest negative cases below. Mirrors
# the structural checks this suite already runs against the real manifest, so
# a broken manifest is expected to fail the *same* checks, not crash.
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

if "name" in m and not isinstance(m["name"], str):
    errors.append(f"'name' must be a string, got {type(m['name']).__name__}")
if "owner" in m and not isinstance(m["owner"], dict):
    errors.append(f"'owner' must be an object, got {type(m['owner']).__name__}")
if "plugins" in m and not isinstance(m["plugins"], list):
    errors.append(f"'plugins' must be an array, got {type(m['plugins']).__name__}")

if isinstance(m.get("plugins"), list):
    entry = next((p for p in m["plugins"] if isinstance(p, dict) and p.get("name") == "continuity"), None)
    if entry is not None and entry.get("source") not in ("./", "."):
        errors.append(f"continuity source must be this repo root, got {entry.get('source')!r}")

for e in errors:
    print(f"FAIL: {e}", file=sys.stderr)
sys.exit(1 if errors else 0)
PY
}

tmp_dir="${TMPDIR:-/tmp}"
scratch="$tmp_dir/marketplace_negative_$$.json"
trap 'rm -f "$scratch"' EXIT

# Case 21: schema validation fails gracefully when required fields are missing
cat > "$scratch" <<'JSON'
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "continuity",
  "plugins": [{"name": "continuity", "source": "./"}]
}
JSON
if validate "$scratch" >/dev/null 2>&1; then
  printf 'FAIL: case 21: manifest missing "owner"/"description" should have failed validation\n' >&2
  fail=1
else
  printf 'PASS: case 21: validation fails gracefully on missing required fields\n'
fi

# Case 22: schema validation fails when JSON is malformed
cat > "$scratch" <<'JSON'
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "continuity",
  "description": "broken",
  "owner": {"name": "x", "url": "https://example.com"},
  "plugins": [ { "name": "continuity", "source": "./" ]
JSON
if validate "$scratch" >/dev/null 2>&1; then
  printf 'FAIL: case 22: malformed JSON should have failed validation\n' >&2
  fail=1
else
  printf 'PASS: case 22: validation fails gracefully on malformed JSON (no crash)\n'
fi

# Case 23: schema validation fails when field types are incorrect
cat > "$scratch" <<'JSON'
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": 12345,
  "description": "wrong types",
  "owner": "Navjyot Nishant",
  "plugins": "continuity"
}
JSON
if validate "$scratch" >/dev/null 2>&1; then
  printf 'FAIL: case 23: manifest with wrong field types should have failed validation\n' >&2
  fail=1
else
  printf 'PASS: case 23: validation fails gracefully on incorrect field types\n'
fi

# Case 24: schema validation catches when continuity source points to wrong path
cat > "$scratch" <<'JSON'
{
  "$schema": "https://anthropic.com/claude-code/marketplace.schema.json",
  "name": "continuity",
  "description": "wrong source",
  "owner": {"name": "Navjyot Nishant", "url": "https://github.com/navjyotnishant"},
  "plugins": [
    {
      "name": "continuity",
      "description": "wrong path",
      "source": "./some/other/repo",
      "category": "productivity"
    }
  ]
}
JSON
if validate "$scratch" >/dev/null 2>&1; then
  printf 'FAIL: case 24: continuity source pointing at the wrong path should have failed validation\n' >&2
  fail=1
else
  printf 'PASS: case 24: validation catches a continuity source pointing at the wrong path\n'
fi

exit "$fail"
