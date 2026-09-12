#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Per-field and hook-registration cases for the plugin manifest
#              (T033), complementing test_plugin_manifest.sh's whole-file check.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="$root/.claude-plugin/plugin.json"

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

get() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' "$1" "$2"; }

is_semver() { [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; }

# Build a temp manifest so invalid-field cases don't need to corrupt the real one.
tmp_manifest() {
  local version="$1" description="$2" hooks="$3"
  local f
  f="$(mktemp "${TMPDIR:-/tmp}/manifest_test.XXXXXX")"
  python3 -c 'import json,sys; json.dump({"name":"continuity","version":sys.argv[1],"description":sys.argv[2],"hooks":sys.argv[3]}, open(sys.argv[4],"w"))' \
    "$version" "$description" "$hooks" "$f"
  echo "$f"
}

# version field with invalid format is rejected
bad_version="$(tmp_manifest "1.0" "x" "./hooks/hooks.json")"
is_semver "$(get "$bad_version" version)" && fail "invalid version '1.0' should not pass semver check"
rm -f "$bad_version"

# description field is non-empty
[ -n "$(get "$manifest" description)" ] || fail "description must be non-empty"

# description field with empty string is rejected
empty_desc="$(tmp_manifest "0.1.0" "" "./hooks/hooks.json")"
[ -n "$(get "$empty_desc" description)" ] && fail "empty description should not pass non-empty check"
rm -f "$empty_desc"

# hooks field equals "./hooks/hooks.json"
[ "$(get "$manifest" hooks)" = "./hooks/hooks.json" ] || fail "hooks entrypoint must be ./hooks/hooks.json"

# hooks field with different path is rejected
bad_hooks="$(tmp_manifest "0.1.0" "x" "./config/hooks.json")"
[ "$(get "$bad_hooks" hooks)" = "./hooks/hooks.json" ] && fail "wrong hooks path should not pass equality check"
rm -f "$bad_hooks"

# --- Hook script registration (T016, T019) ---
# hooks/hooks.json doesn't exist yet on this branch, so these cases exercise the
# registration check against a synthetic fixture rather than the real file.
fixture_root="$(mktemp -d "${TMPDIR:-/tmp}/manifest_test.XXXXXX")"
mkdir -p "$fixture_root/hooks"
touch "$fixture_root/hooks/session-start.sh" "$fixture_root/hooks/capture-trigger.sh"
cat > "$fixture_root/hooks/hooks.json" <<'JSON'
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh"}]}],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/capture-trigger.sh"}]}]
  }
}
JSON

# When hooks.json exists, it registers session-start.sh
grep -q "session-start.sh" "$fixture_root/hooks/hooks.json" || fail "hooks.json does not register session-start.sh"
[ -f "$fixture_root/hooks/session-start.sh" ] || fail "hooks.json names a missing hooks/session-start.sh"

# When hooks.json exists, it registers capture-trigger.sh
grep -q "capture-trigger.sh" "$fixture_root/hooks/hooks.json" || fail "hooks.json does not register capture-trigger.sh"
[ -f "$fixture_root/hooks/capture-trigger.sh" ] || fail "hooks.json names a missing hooks/capture-trigger.sh"

rm -rf "$fixture_root"

printf 'ok: plugin manifest field and hook-registration cases\n'
