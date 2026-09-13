#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Asserts .claude-plugin/plugin.json is a valid Claude Code plugin
#              manifest and that its hook wiring reaches every hook script.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
manifest="$root/.claude-plugin/plugin.json"

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

[ -f "$manifest" ] || fail "missing $manifest"
python3 -m json.tool "$manifest" >/dev/null 2>&1 || fail "plugin.json is not valid JSON"

get() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' "$manifest" "$1"; }

[ "$(get name)" = "continuity" ] || fail "name must be 'continuity'"
[[ "$(get version)" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || fail "version must be semver"
[ -n "$(get description)" ] || fail "description must be non-empty"

hooks="$(get hooks)"
[ "$hooks" = "./hooks/hooks.json" ] || fail "hooks entrypoint must be ./hooks/hooks.json"

# The manifest names the hook scripts through its entrypoint, so the two are only
# consistent once hooks.json exists (T023). Until then there is nothing to check.
hooks_json="$root/${hooks#./}"
if [ -f "$hooks_json" ]; then
  for script in session-start.sh capture-trigger.sh session-end.sh; do
    grep -q "$script" "$hooks_json" || fail "hooks.json does not register $script"
    [ -f "$root/hooks/$script" ] || fail "hooks.json names a missing hooks/$script"
  done
else
  printf 'note: %s absent, hook-script wiring not yet checkable\n' "$hooks_json"
fi

printf 'ok: plugin manifest\n'
