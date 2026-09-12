#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Asserts .claude-plugin/plugin.json's JSON structure and field
#              values are valid, and that malformed/wrong variants are rejected.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="$root/.claude-plugin/plugin.json"

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

is_valid_json() { python3 -m json.tool "$1" >/dev/null 2>&1; }
get() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' "$1" "$2"; }

# plugin.json parses as valid JSON
[ -f "$manifest" ] || fail "missing $manifest"
is_valid_json "$manifest" || fail "plugin.json is not valid JSON"

# Invalid JSON syntax is rejected
tmp_invalid="$(mktemp "${TMPDIR:-/tmp}/manifest_test.XXXXXX")"
trap 'rm -f "$tmp_invalid" "$tmp_bad_name"' EXIT
printf '{ "name": "continuity", ' > "$tmp_invalid"
is_valid_json "$tmp_invalid" && fail "malformed JSON was accepted as valid"

# All required fields (name, version, description, hooks) are present
for field in name version description hooks; do
  [ -n "$(get "$manifest" "$field")" ] || fail "required field '$field' is missing or empty"
done

# name field equals "continuity"
[ "$(get "$manifest" name)" = "continuity" ] || fail "name must be 'continuity'"

# name field with different value is rejected
tmp_bad_name="$(mktemp "${TMPDIR:-/tmp}/manifest_test.XXXXXX")"
python3 -c '
import json, sys
d = json.load(open(sys.argv[1]))
d["name"] = "not-continuity"
json.dump(d, open(sys.argv[2], "w"))
' "$manifest" "$tmp_bad_name"
[ "$(get "$tmp_bad_name" name)" = "continuity" ] && fail "manifest with wrong name was accepted"

# version field is valid semver format (X.Y.Z)
[[ "$(get "$manifest" version)" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "version must be semver X.Y.Z"

printf 'ok: plugin manifest JSON validation\n'
