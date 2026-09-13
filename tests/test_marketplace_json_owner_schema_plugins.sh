#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Validates .claude-plugin/marketplace.json's owner object shape,
#              $schema value, and plugins array shape (T034 cases 7-12). Takes
#              an optional manifest path (default: the repo's own), so a
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

python3 - "$manifest" <<'PY' || exit 1
import json, sys
from urllib.parse import urlparse

EXPECTED_SCHEMA = "https://anthropic.com/claude-code/marketplace.schema.json"

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

# Case 7: owner field is an object (not null, string, or array)
owner = m.get("owner")
if not isinstance(owner, dict):
    errors.append(f"case 7: owner must be an object, got {type(owner).__name__}")

# Case 8: owner.name exists and is a non-empty string
if isinstance(owner, dict):
    name = owner.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("case 8: owner.name must be a non-empty string")

# Case 9: owner.url exists and is a valid URL format
if isinstance(owner, dict):
    url = owner.get("url")
    if not isinstance(url, str) or not url.strip():
        errors.append("case 9: owner.url must be a non-empty string")
    else:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            errors.append(f"case 9: owner.url is not a valid URL, got {url!r}")

# Case 10: $schema field points to the correct Claude Code marketplace schema URL
schema = m.get("$schema")
if schema != EXPECTED_SCHEMA:
    errors.append(f"case 10: $schema must be {EXPECTED_SCHEMA!r}, got {schema!r}")

# Case 11: plugins field is an array (not null, object, or string)
plugins = m.get("plugins")
if not isinstance(plugins, list):
    errors.append(f"case 11: plugins must be an array, got {type(plugins).__name__}")

# Case 12: plugins array contains at least one entry
if isinstance(plugins, list) and len(plugins) < 1:
    errors.append("case 12: plugins array must contain at least one entry")

for e in errors:
    print(f"FAIL: {e}", file=sys.stderr)
sys.exit(1 if errors else 0)
PY

printf 'PASS: test_marketplace_json_owner_schema_plugins.sh (%s)\n' "$manifest"
