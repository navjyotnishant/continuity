#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Asserts the five seed templates exist and carry the field shapes
#              data-model.md requires (T008).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATES="$ROOT/templates"
fails=0

check() { # check <message> <command...>
  local msg="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "ok   - $msg"
  else
    echo "FAIL - $msg"
    fails=$((fails + 1))
  fi
}

for f in state.md.tmpl decisions.md.tmpl tasks.md.tmpl learnings.md.tmpl \
         metadata.json.tmpl; do
  check "templates/$f exists and is non-empty" test -s "$TEMPLATES/$f"
done

# metadata.json.tmpl must be parseable JSON with schema_version 1.0, so that
# lib/migrate.sh (T007) can seed metadata.json from it verbatim.
if command -v python3 >/dev/null 2>&1; then
  check "metadata.json.tmpl is valid JSON" \
    python3 -m json.tool "$TEMPLATES/metadata.json.tmpl"
  check "metadata.json.tmpl has schema_version 1.0 and the configurable keys" \
    python3 -c '
import json, sys
m = json.load(open(sys.argv[1]))
assert m["schema_version"] == "1.0", m["schema_version"]
assert m["retention_days"] == 60, m["retention_days"]
assert m["git_tracked"] is True, m["git_tracked"]
for k in ("plugin_version", "created_at"):
    assert isinstance(m[k], str) and m[k], k
' "$TEMPLATES/metadata.json.tmpl"
else
  echo "skip - no python3; JSON validation not run"
fi

# Section headings the write path appends into (data-model.md: Constraints fold
# into state.md, Conventions into learnings.md).
check "state.md.tmpl has an updated_at field" \
  grep -q '^updated_at:' "$TEMPLATES/state.md.tmpl"
check "state.md.tmpl has a '## Constraints' section" \
  grep -q '^## Constraints$' "$TEMPLATES/state.md.tmpl"
check "learnings.md.tmpl has a '## Conventions' section" \
  grep -q '^## Conventions$' "$TEMPLATES/learnings.md.tmpl"

# A seed store must start with no entries — a template entry would be read back
# as real project memory by select_context.sh.
for f in decisions.md.tmpl tasks.md.tmpl; do
  check "$f seeds no entries" bash -c \
    "! grep -qE '^## ' '$TEMPLATES/$f'"
done
check "learnings.md.tmpl seeds no entries beyond '## Conventions'" bash -c \
  "! grep -E '^## ' '$TEMPLATES/learnings.md.tmpl' | grep -qv '^## Conventions$'"

if [ "$fails" -ne 0 ]; then
  echo "test_templates.sh: $fails assertion(s) failed"
  exit 1
fi
echo "test_templates.sh: all assertions passed"
