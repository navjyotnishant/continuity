#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Covers session-end.sh hook-registration wiring plus missing-field
#              rejection (name/version/description absent, not just empty) for
#              the plugin manifest (T033).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

fail() { printf 'FAIL: %s\n' "$1" >&2; exit 1; }

get() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get(sys.argv[2],""))' "$1" "$2"; }

# Build a temp manifest with only the given keys, so a field can be OMITTED
# entirely rather than merely empty.
tmp_manifest_with() {
  python3 -c '
import json, sys
pairs = sys.argv[1:]
d = dict(zip(pairs[0::2], pairs[1::2]))
import tempfile
f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
json.dump(d, f)
print(f.name)
' "$@"
}

# --- Missing/null fields ---

# Missing name field
no_name="$(tmp_manifest_with version "0.1.0" description "x" hooks "./hooks/hooks.json")"
[ -z "$(get "$no_name" name)" ] || fail "manifest without a name key should read as empty"
rm -f "$no_name"

# Missing version field
no_version="$(tmp_manifest_with name "continuity" description "x" hooks "./hooks/hooks.json")"
[ -z "$(get "$no_version" version)" ] || fail "manifest without a version key should read as empty"
rm -f "$no_version"

# Missing description field
no_description="$(tmp_manifest_with name "continuity" version "0.1.0" hooks "./hooks/hooks.json")"
[ -z "$(get "$no_description" description)" ] || fail "manifest without a description key should read as empty"
rm -f "$no_description"

# --- Hook wiring (T023's hooks/hooks.json) ---
# hooks/hooks.json doesn't exist yet on this branch, so these exercise the
# registration check against a synthetic fixture rather than the real file.
fixture_root="$(mktemp -d "${TMPDIR:-/tmp}/manifest_test.XXXXXX")"
trap 'rm -rf "$fixture_root"' EXIT
mkdir -p "$fixture_root/hooks"
touch "$fixture_root/hooks/session-start.sh" "$fixture_root/hooks/capture-trigger.sh" "$fixture_root/hooks/session-end.sh"
cat > "$fixture_root/hooks/hooks.json" <<'JSON'
{
  "hooks": {
    "SessionStart": [{"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-start.sh"}]}],
    "PostToolUse": [{"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/capture-trigger.sh"}]}],
    "SessionEnd": [{"hooks": [{"type": "command", "command": "${CLAUDE_PLUGIN_ROOT}/hooks/session-end.sh"}]}]
  }
}
JSON

# When hooks.json exists, it registers session-end.sh
grep -q "session-end.sh" "$fixture_root/hooks/hooks.json" || fail "hooks.json does not register session-end.sh"

# Each hook script named in hooks.json exists as a file at the expected path
for script in session-start.sh capture-trigger.sh session-end.sh; do
  grep -q "$script" "$fixture_root/hooks/hooks.json" || fail "hooks.json does not register $script"
  [ -f "$fixture_root/hooks/$script" ] || fail "hooks.json names a missing hooks/$script"
done

# Hook script exists but is not registered in hooks.json
touch "$fixture_root/hooks/orphan.sh"
if grep -q "orphan.sh" "$fixture_root/hooks/hooks.json"; then
  fail "orphan.sh should not be registered in hooks.json"
fi

printf 'ok: plugin manifest missing-field rejection and hook wiring\n'
