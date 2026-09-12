#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Asserts the five seed templates (T008) share consistent
#              metadata/markdown/JSON formatting per file-format-contract.md.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TEMPLATES="$ROOT/templates"
MD_TEMPLATES="state.md.tmpl decisions.md.tmpl tasks.md.tmpl learnings.md.tmpl"
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

FENCE='```'

# --- Case: consistent field/metadata syntax (fenced code blocks) -----------

check "state.md.tmpl's updated_at field sits inside a fenced code block" bash -c "
  awk -v fence=\"\$FENCE\" 'index(\$0, fence) == 1 { f = !f } f && /^updated_at:/ { found = 1 } END { exit !found }' \"\$TEMPLATES/state.md.tmpl\"
"

for f in decisions.md.tmpl tasks.md.tmpl learnings.md.tmpl; do
  check "$f documents metadata fields only in prose, never as bare field: lines" bash -c "
    ! grep -qE '^(captured_at|category|status|updated_at):' \"\$TEMPLATES/$f\"
  "
done

# --- Case: placeholder timestamps follow ISO-8601 UTC where documented -----

check "state.md.tmpl's updated_at placeholder reads <ISO-8601 UTC timestamp>" \
  grep -qF '<ISO-8601 UTC timestamp>' "$TEMPLATES/state.md.tmpl"
check "metadata.json.tmpl's created_at placeholder reads <ISO-8601 UTC timestamp>" \
  grep -qF '"<ISO-8601 UTC timestamp>"' "$TEMPLATES/metadata.json.tmpl"
for f in decisions.md.tmpl tasks.md.tmpl learnings.md.tmpl; do
  check "$f mentions the captured_at field" \
    grep -qF 'captured_at' "$TEMPLATES/$f"
  check "$f documents its timestamp field(s) as ISO-8601 UTC" \
    grep -qF 'ISO-8601 UTC' "$TEMPLATES/$f"
done

# --- Case: UTF-8 encoding, LF line endings ---------------------------------

for f in $MD_TEMPLATES metadata.json.tmpl; do
  check "$f has no CR characters (LF line endings)" bash -c "
    ! grep -qU \$'\r' \"\$TEMPLATES/$f\"
  "
  if command -v iconv >/dev/null 2>&1; then
    check "$f is valid UTF-8" bash -c "
      iconv -f UTF-8 -t UTF-8 \"\$TEMPLATES/$f\" >/dev/null
    "
  fi
  check "$f ends with a trailing newline" bash -c "
    test -z \"\$(tail -c 1 \"\$TEMPLATES/$f\")\"
  "
done

# --- Case: markdown templates parse with no syntax errors ------------------

for f in $MD_TEMPLATES; do
  check "$f has a balanced number of fenced-code-block markers" bash -c "
    n=\$(grep -c '^\`\`\`' \"\$TEMPLATES/$f\"); test \$((n % 2)) -eq 0
  "
  check "$f has no unmatched HTML comment markers" bash -c "
    o=\$(grep -o '<!--' \"\$TEMPLATES/$f\" | wc -l); c=\$(grep -o '\-\->' \"\$TEMPLATES/$f\" | wc -l); test \"\$o\" -eq \"\$c\"
  "
  check "$f's headings are well-formed (# followed by a space)" bash -c "
    ! grep -qE '^#+[^# ]' \"\$TEMPLATES/$f\"
  "
  check "$f starts with a top-level # heading" bash -c "
    head -n1 \"\$TEMPLATES/$f\" | grep -qE '^# '
  "
done

# --- Case: JSON template stays valid once a template engine substitutes ----

if command -v python3 >/dev/null 2>&1; then
  check "metadata.json.tmpl remains valid JSON after placeholder substitution" bash -c "
    sed -e 's/<semver of the installed plugin>/0.1.0/' -e 's/<ISO-8601 UTC timestamp>/2026-09-12T00:00:00Z/' \"\$TEMPLATES/metadata.json.tmpl\" | python3 -m json.tool
  "
else
  echo "skip - no python3; post-substitution JSON validation not run"
fi

if [ "$fails" -ne 0 ]; then
  echo "test_templates_format.sh: $fails assertion(s) failed"
  exit 1
fi
echo "test_templates_format.sh: all assertions passed"
