#!/usr/bin/env bash
# tests/test_common.sh — covers lib/common.sh's three functions.
# Sourced by run_tests.sh (not executed), so no `exit` here — assertions
# report failures via assert_eq/assert_ok, defined by the caller.

. "$CONTINUITY_REPO_ROOT/lib/common.sh"

test_common_continuity_dir() {
  assert_eq "/tmp/some-project/.continuity" "$(continuity_dir /tmp/some-project)" \
    "continuity_dir strips nothing extra for a plain path"
  assert_eq "/tmp/some-project/.continuity" "$(continuity_dir /tmp/some-project/)" \
    "continuity_dir strips a trailing slash"
}

test_common_continuity_log() {
  local fixture
  fixture="$(mktemp -d "${TMPDIR:-/tmp}/continuity-test.XXXXXX")"

  continuity_log "$fixture" "session-start" "read-error" "fixture detail"
  assert_ok "$?" "continuity_log returns success on a writable dir"
  assert_eq "1" "$(wc -l < "$fixture/errors.log" | tr -d ' ')" \
    "continuity_log appends exactly one line"
  assert_eq "1" "$(grep -c 'session-start | read-error | fixture detail' "$fixture/errors.log")" \
    "continuity_log writes the pipe-delimited fields verbatim"

  continuity_log "$fixture" 'op|with|pipes' 'kind
with-newline' 'detail'
  assert_eq "2" "$(wc -l < "$fixture/errors.log" | tr -d ' ')" \
    "continuity_log still appends exactly one more line when fields contain pipes/newlines"

  rm -rf "$fixture"
}

test_common_continuity_log_fails_open() {
  local fixture
  fixture="$(mktemp -d "${TMPDIR:-/tmp}/continuity-test.XXXXXX")"
  chmod 000 "$fixture"

  continuity_log "$fixture/nested/.continuity" "op" "kind" "detail"
  assert_ok "$?" "continuity_log no-ops (still returns 0) when it cannot create its dir"

  chmod 755 "$fixture"
  rm -rf "$fixture"
}

test_common_metadata_defaults() {
  local fixture
  fixture="$(mktemp -d "${TMPDIR:-/tmp}/continuity-test.XXXXXX")"

  continuity_metadata_read "$fixture"
  assert_eq "60" "$CONTINUITY_RETENTION_DAYS" \
    "continuity_metadata_read defaults retention_days to 60 when metadata.json is absent"
  assert_eq "true" "$CONTINUITY_GIT_TRACKED" \
    "continuity_metadata_read defaults git_tracked to true when metadata.json is absent"

  cat > "$fixture/metadata.json" <<'EOF'
{
  "schema_version": "1.0",
  "plugin_version": "0.1.0",
  "created_at": "2026-09-12T00:00:00Z",
  "retention_days": 30,
  "git_tracked": false
}
EOF
  continuity_metadata_read "$fixture"
  assert_eq "30" "$CONTINUITY_RETENTION_DAYS" \
    "continuity_metadata_read reads a present retention_days"
  assert_eq "false" "$CONTINUITY_GIT_TRACKED" \
    "continuity_metadata_read reads a present git_tracked"

  echo 'not valid json at all' > "$fixture/metadata.json"
  continuity_metadata_read "$fixture"
  assert_eq "60" "$CONTINUITY_RETENTION_DAYS" \
    "continuity_metadata_read falls back to the default on unparseable content"

  rm -rf "$fixture"
}

test_common_continuity_dir
test_common_continuity_log
test_common_continuity_log_fails_open
test_common_metadata_defaults
