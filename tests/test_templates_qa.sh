#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Independent QA pass over the five seed templates (T008/CONTINUI-31),
#              covering acceptance cases the existing test_templates.sh /
#              test_templates_format.sh either missed or check incorrectly
#              (see the QA report for the specific gaps: broken $TEMPLATES/$FENCE
#              scoping inside nested `bash -c` in test_templates_format.sh, and
#              a comment-line false-positive in test_templates.sh's placeholder
#              balance check). This file does not touch those existing files.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATES="$ROOT/templates"
fails=0

check() {
  local msg="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "ok   - $msg"
  else
    echo "FAIL - $msg"
    fails=$((fails + 1))
  fi
}

# --- Case: exactly the five expected files, no more, no less ---------------

check "templates/ contains exactly the five expected *.tmpl files, nothing else" \
  python3 -c '
import glob, sys
expected = {"state.md.tmpl", "decisions.md.tmpl", "tasks.md.tmpl",
            "learnings.md.tmpl", "metadata.json.tmpl"}
actual = {p.split("/")[-1] for p in glob.glob(sys.argv[1] + "/*")}
assert actual == expected, actual
' "$TEMPLATES"

# --- Case: JSON field types are exact, not just equal-by-coercion ----------
# json.load collapses duplicate keys (last wins) and Python's == treats
# 60 == 60.0 == True == 1, so the existing suite's equality asserts would not
# catch a wrong type or a duplicate key. Check both explicitly.

check "metadata.json.tmpl has no duplicate top-level keys in the raw text" \
  python3 -c '
import re, sys
text = open(sys.argv[1]).read()
keys = re.findall(r"^\s*\"(\w+)\"\s*:", text, re.MULTILINE)
assert len(keys) == len(set(keys)), keys
' "$TEMPLATES/metadata.json.tmpl"

check "metadata.json.tmpl: retention_days is a JSON integer, not a string/float" \
  python3 -c '
import json, sys
m = json.load(open(sys.argv[1]))
assert type(m["retention_days"]) is int, type(m["retention_days"])
assert m["retention_days"] == 60
' "$TEMPLATES/metadata.json.tmpl"

check "metadata.json.tmpl: schema_version is a JSON string, not a number" \
  python3 -c '
import json, sys
m = json.load(open(sys.argv[1]))
assert type(m["schema_version"]) is str, type(m["schema_version"])
assert m["schema_version"] == "1.0"
' "$TEMPLATES/metadata.json.tmpl"

check "metadata.json.tmpl: git_tracked is a JSON boolean, not a string" \
  python3 -c '
import json, sys
m = json.load(open(sys.argv[1]))
assert type(m["git_tracked"]) is bool, type(m["git_tracked"])
assert m["git_tracked"] is True
' "$TEMPLATES/metadata.json.tmpl"

# --- Case: seeded-section bodies are actually empty, not just "heading exists" --
# The existing suite checks the '## Constraints' / '## Conventions' headings
# exist and that decisions/tasks have no headings at all, but never checks
# whether *bullet content* was seeded under Constraints/Conventions (a bullet
# is not a '## ' heading, so the existing "seeds no entries" checks can't see it).

check "state.md.tmpl's '## Constraints' section has no seeded bullet entries" \
  python3 -c '
import sys
lines = open(sys.argv[1]).read().splitlines()
i = lines.index("## Constraints")
body = lines[i+1:]
for line in body:
    s = line.strip()
    if s.startswith("-") or s.startswith("*"):
        raise AssertionError("seeded bullet found: " + line)
' "$TEMPLATES/state.md.tmpl"

check "learnings.md.tmpl's '## Conventions' section has no seeded bullet entries" \
  python3 -c '
import sys
lines = open(sys.argv[1]).read().splitlines()
i = lines.index("## Conventions")
body = lines[i+1:]
for line in body:
    s = line.strip()
    if s.startswith("-") or s.startswith("*"):
        raise AssertionError("seeded bullet found: " + line)
' "$TEMPLATES/learnings.md.tmpl"

# --- Case: UTF-8 encoding and LF-only line endings (checked directly, no
# nested bash -c with unexported variables, unlike test_templates_format.sh) --

for f in state.md.tmpl decisions.md.tmpl tasks.md.tmpl learnings.md.tmpl \
         metadata.json.tmpl; do
  check "$f decodes as valid UTF-8" \
    python3 -c '
import sys
open(sys.argv[1], encoding="utf-8").read()
' "$TEMPLATES/$f"
  check "$f has no CR bytes (LF-only line endings)" \
    python3 -c '
import sys
data = open(sys.argv[1], "rb").read()
assert b"\r" not in data
' "$TEMPLATES/$f"
done

# --- Case: markdown starts with a top-level heading and headings are
# well-formed (checked directly against the real path) ---------------------

for f in state.md.tmpl decisions.md.tmpl tasks.md.tmpl learnings.md.tmpl; do
  check "$f starts with a top-level '# ' heading" \
    python3 -c '
import sys
first = open(sys.argv[1]).readline()
assert first.startswith("# "), first
' "$TEMPLATES/$f"
done

# --- Case: metadata.json.tmpl round-trips through placeholder substitution
# (checked directly, unlike the broken $TEMPLATES-in-bash-c version) -------

check "metadata.json.tmpl stays valid JSON after substituting its placeholders" \
  python3 -c '
import json, re, sys
text = open(sys.argv[1]).read()
text = text.replace("<semver of the installed plugin>", "0.1.0")
text = text.replace("<ISO-8601 UTC timestamp>", "2026-09-12T00:00:00Z")
assert "<" not in text and ">" not in text, "placeholders left after substitution"
json.loads(text)
' "$TEMPLATES/metadata.json.tmpl"

# --- Case: placeholder delimiters are balanced, excluding HTML comment
# markers ("<!--"/"-->") which the existing suite'\''s generic '<'\''/'\''>'\''
# line scan misreads as an unclosed placeholder ------------------------------

for f in state.md.tmpl decisions.md.tmpl tasks.md.tmpl learnings.md.tmpl \
         metadata.json.tmpl; do
  check "$f's non-comment '<...>' placeholders are all closed on their line" \
    python3 -c '
import re, sys
text = open(sys.argv[1]).read()
# Drop HTML comments (which legitimately open/close "<" across lines).
text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
for lineno, line in enumerate(text.splitlines(), 1):
    if "<" in line or ">" in line:
        assert line.count("<") == line.count(">"), (lineno, line)
' "$TEMPLATES/$f"
done

if [ "$fails" -ne 0 ]; then
  echo "test_templates_qa.sh: $fails assertion(s) failed"
  exit 1
fi
echo "test_templates_qa.sh: all assertions passed"
