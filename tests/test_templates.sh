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
  check "metadata.json.tmpl has no fields beyond the five known keys" \
    python3 -c '
import json, sys
m = json.load(open(sys.argv[1]))
known = {"schema_version", "retention_days", "git_tracked", "plugin_version", "created_at"}
assert set(m.keys()) == known, sorted(m.keys())
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

# Section heading names must match what data-model.md documents and what
# select_context.sh (T009+) will look for when it reads these files back.
check "state.md.tmpl heading matches data-model.md's '## Constraints'" \
  grep -q '^## Constraints$' "$TEMPLATES/state.md.tmpl"
check "learnings.md.tmpl heading matches data-model.md's '## Conventions'" \
  grep -q '^## Conventions$' "$TEMPLATES/learnings.md.tmpl"
check "data-model.md itself documents '## Constraints' for state.md" \
  grep -q '## Constraints' "$ROOT/specs/001-continuity/data-model.md"
check "data-model.md itself documents '## Conventions' for learnings.md" \
  grep -q '## Conventions' "$ROOT/specs/001-continuity/data-model.md"

# Permissions: templates must be readable and never executable — nothing
# instantiates them by running them, so an execute bit would be an accident
# waiting to be invoked.
for f in state.md.tmpl decisions.md.tmpl tasks.md.tmpl learnings.md.tmpl \
         metadata.json.tmpl; do
  check "templates/$f is readable" test -r "$TEMPLATES/$f"
  check "templates/$f is not executable" bash -c \
    "[ ! -x '$TEMPLATES/$f' ]"
done

# Comments must describe the section they precede, not some other file's
# shape — a copy-pasted comment block would silently document the wrong
# entity.
check "state.md.tmpl's HTML comment mentions the state snapshot, not entries" \
  grep -q 'snapshot' "$TEMPLATES/state.md.tmpl"
check "decisions.md.tmpl's comment names 'Decision:' entries" \
  grep -q 'Decision:' "$TEMPLATES/decisions.md.tmpl"
check "tasks.md.tmpl's comment names 'Task:' entries and a status enum" \
  grep -q 'Task:' "$TEMPLATES/tasks.md.tmpl"
check "tasks.md.tmpl's comment documents the status enum" \
  grep -qE 'active \| blocked \| done' "$TEMPLATES/tasks.md.tmpl"
check "learnings.md.tmpl's comment names 'Learning:' entries" \
  grep -q 'Learning:' "$TEMPLATES/learnings.md.tmpl"
check "learnings.md.tmpl's Conventions comment names 'Convention:' entries" \
  bash -c "sed -n '/## Conventions/,\$p' '$TEMPLATES/learnings.md.tmpl' | grep -q 'Convention:'"

# No template may hardcode a value that data-model.md says is filled in at
# instantiation time (timestamps, versions) -- those must stay placeholders.
check "state.md.tmpl's updated_at is a placeholder, not a real timestamp" \
  grep -qE '^updated_at: <.*>$' "$TEMPLATES/state.md.tmpl"
check "metadata.json.tmpl's created_at is a placeholder, not a real timestamp" \
  grep -qE '"created_at": *"<[^"]*>"' "$TEMPLATES/metadata.json.tmpl"
check "metadata.json.tmpl's plugin_version is a placeholder, not a pinned version" \
  grep -qE '"plugin_version": *"<[^"]*>"' "$TEMPLATES/metadata.json.tmpl"
check "metadata.json.tmpl's static config values are literal, not placeholders" \
  bash -c \
  "! grep -qE '\"(schema_version|retention_days|git_tracked)\": *\"?<' '$TEMPLATES/metadata.json.tmpl'"

# Placeholder delimiters must be balanced: every '<' in a template's
# instantiation-time value has a matching '>' on the same line, and vice
# versa, so a substitution pass can't run off the end of the line.
for f in state.md.tmpl decisions.md.tmpl tasks.md.tmpl learnings.md.tmpl \
         metadata.json.tmpl; do
  check "$f has balanced '<' and '>' counts" bash -c \
    "[ \$(grep -o '<' '$TEMPLATES/$f' | wc -l) -eq \$(grep -o '>' '$TEMPLATES/$f' | wc -l) ]"
  check "$f has no line with an unclosed '<...>' placeholder" bash -c \
    "! grep -nE '<[^>]*\$' '$TEMPLATES/$f'"
done

if [ "$fails" -ne 0 ]; then
  echo "test_templates.sh: $fails assertion(s) failed"
  exit 1
fi
echo "test_templates.sh: all assertions passed"
