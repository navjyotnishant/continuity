#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Missing/null-field and type-violation cases for the plugin
#              manifest (T033), complementing test_plugin_manifest_cases.sh.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

is_valid_json() { python3 -m json.tool "$1" >/dev/null 2>&1; }

# has_required_string_field <file> <field>: true only if the field is present
# AND is a non-empty JSON string (mirrors what a real loader must enforce).
has_required_string_field() {
  python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
v = d.get(sys.argv[2], "__MISSING__")
sys.exit(0 if (v != "__MISSING__" and isinstance(v, str) and v != "") else 1)
' "$1" "$2"
}

write_manifest() {
  # write_manifest <outfile> <python-dict-literal-building-code>
  local out="$1" build="$2"
  python3 -c "
import json
d = {'name': 'continuity', 'version': '0.1.0', 'description': 'x', 'hooks': './hooks/hooks.json'}
$build
json.dump(d, open('$out', 'w'))
"
}

tmp_files=()
cleanup() { rm -f "${tmp_files[@]:-}"; }
trap cleanup EXIT

new_tmp() { local f; f="$(mktemp "${TMPDIR:-/tmp}/manifest_test.XXXXXX")"; tmp_files+=("$f"); echo "$f"; }

# --- Missing hooks field ---
f="$(new_tmp)"
write_manifest "$f" "del d['hooks']"
is_valid_json "$f" || fail "manifest missing hooks should still be valid JSON"
has_required_string_field "$f" hooks && fail "manifest missing hooks field was accepted"

# --- name field is null ---
f="$(new_tmp)"
write_manifest "$f" "d['name'] = None"
is_valid_json "$f" || fail "manifest with null name should still be valid JSON"
has_required_string_field "$f" name && fail "manifest with null name was accepted"

# --- version field is null ---
f="$(new_tmp)"
write_manifest "$f" "d['version'] = None"
is_valid_json "$f" || fail "manifest with null version should still be valid JSON"
has_required_string_field "$f" version && fail "manifest with null version was accepted"

# --- description field is null ---
f="$(new_tmp)"
write_manifest "$f" "d['description'] = None"
is_valid_json "$f" || fail "manifest with null description should still be valid JSON"
has_required_string_field "$f" description && fail "manifest with null description was accepted"

# --- hooks field is null ---
f="$(new_tmp)"
write_manifest "$f" "d['hooks'] = None"
is_valid_json "$f" || fail "manifest with null hooks should still be valid JSON"
has_required_string_field "$f" hooks && fail "manifest with null hooks was accepted"

# --- Type violations: name is not a string ---
f="$(new_tmp)"
write_manifest "$f" "d['name'] = 42"
is_valid_json "$f" || fail "manifest with numeric name should still be valid JSON"
has_required_string_field "$f" name && fail "manifest with numeric name was accepted"

f="$(new_tmp)"
write_manifest "$f" "d['name'] = {'value': 'continuity'}"
is_valid_json "$f" || fail "manifest with object name should still be valid JSON"
has_required_string_field "$f" name && fail "manifest with object name was accepted"

f="$(new_tmp)"
write_manifest "$f" "d['name'] = ['continuity']"
is_valid_json "$f" || fail "manifest with array name should still be valid JSON"
has_required_string_field "$f" name && fail "manifest with array name was accepted"

printf 'ok: plugin manifest missing/null-field and type-violation cases\n'
