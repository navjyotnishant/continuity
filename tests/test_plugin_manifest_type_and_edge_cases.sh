#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Type-violation cases for version/description/hooks, plus edge
#              cases (extra unknown fields, file location/readability, and
#              graceful handling while hooks/hooks.json is still absent) for
#              the plugin manifest (T033).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="$root/.claude-plugin/plugin.json"

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

has_required_string_field() {
  python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
v = d.get(sys.argv[2], "__MISSING__")
sys.exit(0 if (v != "__MISSING__" and isinstance(v, str) and v != "") else 1)
' "$1" "$2"
}

write_manifest() {
  # write_manifest <outfile> <python-dict-mutation-code>
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

# --- version is not a string ---
f="$(new_tmp)"
write_manifest "$f" "d['version'] = 1"
has_required_string_field "$f" version && fail "manifest with numeric version was accepted"

f="$(new_tmp)"
write_manifest "$f" "d['version'] = ['0','1','0']"
has_required_string_field "$f" version && fail "manifest with array version was accepted"

# --- description is not a string ---
f="$(new_tmp)"
write_manifest "$f" "d['description'] = 42"
has_required_string_field "$f" description && fail "manifest with numeric description was accepted"

f="$(new_tmp)"
write_manifest "$f" "d['description'] = {'text': 'x'}"
has_required_string_field "$f" description && fail "manifest with object description was accepted"

# --- hooks is not a string ---
f="$(new_tmp)"
write_manifest "$f" "d['hooks'] = 1"
has_required_string_field "$f" hooks && fail "manifest with numeric hooks was accepted"

f="$(new_tmp)"
write_manifest "$f" "d['hooks'] = ['./hooks/hooks.json']"
has_required_string_field "$f" hooks && fail "manifest with array hooks was accepted"

# --- Edge case: extra unknown fields are accepted ---
f="$(new_tmp)"
write_manifest "$f" "d['author'] = 'someone'; d['license'] = 'MIT'; d['repository'] = 'https://example.com'"
for field in name version description hooks; do
  has_required_string_field "$f" "$field" || fail "manifest with extra unknown fields lost required field '$field'"
done

# --- Edge case: file is readable and in the correct location ---
[ -f "$manifest" ] || fail "plugin.json missing at expected path .claude-plugin/plugin.json"
[ -r "$manifest" ] || fail "plugin.json is not readable"
case "$manifest" in
  "$root/.claude-plugin/plugin.json") : ;;
  *) fail "plugin.json resolved to an unexpected path: $manifest" ;;
esac

# --- Edge case: hooks.json does not exist yet (until T023) is handled gracefully ---
hooks_entry="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("hooks",""))' "$manifest")"
hooks_json="$root/${hooks_entry#./}"
if [ ! -f "$hooks_json" ]; then
  printf 'note: %s absent, hook-script wiring not yet checkable\n' "$hooks_json"
else
  printf 'note: %s already exists, skipping the absence case\n' "$hooks_json"
fi

printf 'ok: plugin manifest type-violation and edge cases\n'
