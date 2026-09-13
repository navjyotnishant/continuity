#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Asserts hooks/hooks.json passes manifest validation and that
#              malformed/wrong variants fail it (CONTINUI-12, US2).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
real_hooks_json="$root/hooks/hooks.json"

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

# validate_hooks_json exits 0 for a well-formed hooks.json (valid JSON, all
# three lifecycle events present, every hook entry typed "command" and
# dispatched as "python3 ... ${CLAUDE_PLUGIN_ROOT}/hooks/<script>"), and
# non-zero otherwise. This is the same shape the real hooks.json must pass.
validate_hooks_json() {
  python3 - "$1" <<'PY'
import json, sys

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as handle:
        config = json.load(handle)
except (OSError, ValueError):
    sys.exit(1)

if not isinstance(config, dict) or "hooks" not in config:
    sys.exit(1)

for event in ("SessionStart", "PostToolUse", "SessionEnd"):
    if event not in config["hooks"]:
        sys.exit(1)

for matchers in config["hooks"].values():
    if not isinstance(matchers, list) or not matchers:
        sys.exit(1)
    for matcher in matchers:
        for hook in matcher.get("hooks", []):
            if hook.get("type") != "command":
                sys.exit(1)
            command = hook.get("command", "")
            if not command.startswith("python3 "):
                sys.exit(1)
            if "${CLAUDE_PLUGIN_ROOT}/hooks/" not in command:
                sys.exit(1)

sys.exit(0)
PY
}

# The real hooks.json passes validation.
validate_hooks_json "$real_hooks_json" || fail "the real hooks.json failed validation"

work="$(mktemp -d "${TMPDIR:-/tmp}/hooks_json_invalid.XXXXXX")"
trap 'rm -rf "$work"' EXIT

# Malformed JSON syntax fails validation.
printf '{ "hooks": ' > "$work/malformed.json"
validate_hooks_json "$work/malformed.json" && fail "malformed JSON syntax passed validation"

# Missing a required lifecycle event (SessionEnd) fails validation.
cat > "$work/missing_event.json" <<'JSON'
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/session-start.py\""}]}],
    "PostToolUse": [{"matcher": "Edit|Write|MultiEdit|Bash", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/capture-trigger.py\""}]}]
  }
}
JSON
validate_hooks_json "$work/missing_event.json" && fail "hooks.json missing SessionEnd passed validation"

# A hook entry that is not type "command" fails validation.
cat > "$work/wrong_type.json" <<'JSON'
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "prompt", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/session-start.py\""}]}],
    "PostToolUse": [{"matcher": "Edit|Write|MultiEdit|Bash", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/capture-trigger.py\""}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/session-end.py\""}]}]
  }
}
JSON
validate_hooks_json "$work/wrong_type.json" && fail "hooks.json with a non-command hook type passed validation"

# A command that skips ${CLAUDE_PLUGIN_ROOT} (a baked-in path) fails validation.
cat > "$work/baked_in_path.json" <<'JSON'
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "python3 /opt/continuity/hooks/session-start.py"}]}],
    "PostToolUse": [{"matcher": "Edit|Write|MultiEdit|Bash", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/capture-trigger.py\""}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/session-end.py\""}]}]
  }
}
JSON
validate_hooks_json "$work/baked_in_path.json" && fail "hooks.json with a baked-in path passed validation"

# A command not dispatched via python3 fails validation.
cat > "$work/no_python3.json" <<'JSON'
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/session-start.py\""}]}],
    "PostToolUse": [{"matcher": "Edit|Write|MultiEdit|Bash", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/capture-trigger.py\""}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/session-end.py\""}]}]
  }
}
JSON
validate_hooks_json "$work/no_python3.json" && fail "hooks.json with a non-python3 dispatch passed validation"

printf 'ok: hooks.json manifest validation\n'
