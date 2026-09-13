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
  python3 -m json.tool "$hooks_json" >/dev/null 2>&1 || fail "hooks.json is not valid JSON"

  for script in session-start.py capture-trigger.py session-end.py; do
    grep -q "$script" "$hooks_json" || fail "hooks.json does not register $script"
    [ -f "$root/hooks/$script" ] || fail "hooks.json names a missing hooks/$script"
  done

  # Each event Continuity needs (research.md R7), with PostToolUse narrowed to
  # the tool calls that can be a meaningful-change signal.
  for event in SessionStart PostToolUse SessionEnd; do
    python3 -c 'import json,sys; sys.exit(0 if sys.argv[2] in json.load(open(sys.argv[1]))["hooks"] else 1)' \
      "$hooks_json" "$event" || fail "hooks.json does not register the $event event"
  done
  python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if any(m.get("matcher")=="Edit|Write|MultiEdit|Bash" for m in d["hooks"]["PostToolUse"]) else 1)' \
    "$hooks_json" || fail "PostToolUse matcher must be Edit|Write|MultiEdit|Bash"

  # A plugin is installed to an arbitrary path, so every command must locate its
  # script through ${CLAUDE_PLUGIN_ROOT} rather than a relative or absolute path,
  # and must name the interpreter explicitly rather than rely on a shebang (R7).
  python3 - "$hooks_json" <<'PY' || fail "every hook command must invoke python3 via \${CLAUDE_PLUGIN_ROOT}"
import json, sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)

for matchers in config["hooks"].values():
    for matcher in matchers:
        for hook in matcher["hooks"]:
            command = hook["command"]
            if hook["type"] != "command":
                sys.exit(1)
            if "${CLAUDE_PLUGIN_ROOT}/hooks/" not in command:
                sys.exit(1)
            if not command.startswith("python3 "):
                sys.exit(1)
PY
else
  printf 'note: %s absent, hook-script wiring not yet checkable\n' "$hooks_json"
fi

printf 'ok: plugin manifest\n'
