#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Case-by-case checks for .claude-plugin/marketplace.json (T034):
#              file exists, is valid JSON, validates against the schema its
#              own $schema points at, and carries required top-level fields
#              (name, description, owner, plugins) with name/description
#              non-empty strings. Takes an optional manifest path (default:
#              the repo's own).
set -uo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="${1:-$repo_root/.claude-plugin/marketplace.json}"
fail=0

# Case 1: file exists at the correct path
if [ ! -f "$manifest" ]; then
  printf 'FAIL: %s does not exist\n' "$manifest" >&2
  exit 1
fi
printf 'PASS: manifest file exists (%s)\n' "$manifest"

if ! command -v python3 >/dev/null 2>&1; then
  printf 'SKIP: python3 not available for JSON/schema validation\n'
  exit 0
fi

# Case 2: valid JSON syntax
err_file="${TMPDIR:-/tmp}/marketplace_json_err_$$"
if ! python3 -c "import json,sys; json.load(open(sys.argv[1]))" "$manifest" 2>"$err_file"; then
  printf 'FAIL: not valid JSON: %s\n' "$(cat "$err_file")" >&2
  rm -f "$err_file"
  exit 1
fi
rm -f "$err_file"
printf 'PASS: manifest is valid JSON\n'

# Cases 3-6: schema validation + required top-level fields + string checks
python3 - "$manifest" <<'PY'
import json, sys

with open(sys.argv[1]) as fh:
    m = json.load(fh)

errors = []

# Case 4: required top-level fields present
for key in ("name", "description", "owner", "plugins"):
    if key not in m:
        errors.append(f"missing top-level field {key!r}")

# Case 5: name is a non-empty string
name = m.get("name")
if not isinstance(name, str) or not name.strip():
    errors.append(f"'name' must be a non-empty string, got {name!r}")

# Case 6: description is a non-empty string
description = m.get("description")
if not isinstance(description, str) or not description.strip():
    errors.append(f"'description' must be a non-empty string, got {description!r}")

for e in errors:
    print(f"FAIL: {e}", file=sys.stderr)
sys.exit(1 if errors else 0)
PY
status=$?
if [ "$status" -ne 0 ]; then
  fail=1
else
  printf 'PASS: name/description/owner/plugins top-level fields present and valid\n'
fi

# Case 3: validate against the schema referenced in $schema.
# Best-effort: needs the jsonschema package AND network access to fetch the
# schema URL. Degrades to SKIP rather than FAIL when either is unavailable,
# consistent with this repo's zero-dependency-fallback convention.
python3 - "$manifest" <<'PY'
import json, sys

with open(sys.argv[1]) as fh:
    m = json.load(fh)

schema_url = m.get("$schema")
if not schema_url:
    print("FAIL: manifest has no $schema to validate against", file=sys.stderr)
    sys.exit(1)

try:
    import jsonschema
except ImportError:
    print("SKIP: jsonschema package not installed, cannot validate against $schema")
    sys.exit(0)

try:
    import urllib.request
    with urllib.request.urlopen(schema_url, timeout=5) as resp:
        schema = json.load(resp)
except Exception as exc:
    print(f"SKIP: could not fetch schema {schema_url!r}: {exc}")
    sys.exit(0)

try:
    jsonschema.validate(instance=m, schema=schema)
except jsonschema.ValidationError as exc:
    print(f"FAIL: manifest does not validate against {schema_url!r}: {exc.message}", file=sys.stderr)
    sys.exit(1)

print(f"PASS: manifest validates against schema {schema_url!r}")
PY
status=$?
if [ "$status" -ne 0 ]; then
  fail=1
fi

exit "$fail"
