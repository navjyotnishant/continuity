#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Unit tests for lib/common.sh — store path resolution, the
#              errors.log append, and the metadata.json config read.

# Assertion helpers are defined only when tests/run_tests.sh has not already
# supplied them, so this file runs both standalone and under that harness.
if ! type assert_eq >/dev/null 2>&1; then
	TESTS_FAILED=0
	assert_eq() {
		if [ "$1" = "$2" ]; then
			printf 'ok   %s\n' "$3"
		else
			printf 'FAIL %s: expected [%s] got [%s]\n' "$3" "$1" "$2"
			TESTS_FAILED=1
		fi
	}
	assert_ok() {
		if [ "$1" -eq 0 ]; then
			printf 'ok   %s\n' "$2"
		else
			printf 'FAIL %s: exit %s\n' "$2" "$1"
			TESTS_FAILED=1
		fi
	}
fi

TEST_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=../lib/common.sh
. "$TEST_DIR/../lib/common.sh"

# Abort rather than continue on a fixture failure: an empty $FIXTURE would
# turn every assertion below into a misleading FAIL against paths like
# "/errors.log".
FIXTURE=$(mktemp -d "${TMPDIR:-/tmp}/continuity-test.XXXXXX") && [ -d "$FIXTURE" ] || {
	printf 'FAIL could not create a temporary fixture directory\n'
	exit 1
}
trap 'rm -rf "$FIXTURE"' EXIT

# --- continuity_dir: path resolution against a fixture project dir ---------
assert_eq "$FIXTURE/.continuity" "$(continuity_dir "$FIXTURE")" \
	"continuity_dir appends .continuity to the project path"
assert_eq "$FIXTURE/.continuity" "$(continuity_dir "$FIXTURE/")" \
	"continuity_dir tolerates a trailing slash"
continuity_dir "" >/dev/null 2>&1
assert_eq "1" "$?" "continuity_dir rejects an empty cwd"

# --- continuity_log: appends one well-shaped line --------------------------
CONTINUITY_DIR=$(continuity_dir "$FIXTURE")
export CONTINUITY_DIR
mkdir -p "$CONTINUITY_DIR"

continuity_log "session-start-load" "corrupted" "state.md missing updated_at"
assert_ok "$?" "continuity_log returns 0 on a successful append"
assert_eq "1" "$(wc -l <"$CONTINUITY_DIR/errors.log" | tr -d ' ')" \
	"continuity_log appends exactly one line"

LINE=$(cat "$CONTINUITY_DIR/errors.log")
assert_eq "session-start-load" "$(printf '%s' "$LINE" | cut -d'|' -f2 | sed 's/^ *//;s/ *$//')" \
	"errors.log field 2 is the operation"
assert_eq "corrupted" "$(printf '%s' "$LINE" | cut -d'|' -f3 | sed 's/^ *//;s/ *$//')" \
	"errors.log field 3 is the failure-kind"
assert_eq "state.md missing updated_at" "$(printf '%s' "$LINE" | cut -d'|' -f4 | sed 's/^ *//;s/ *$//')" \
	"errors.log field 4 is the detail"
case "$LINE" in
[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]Z\ \|*)
	assert_eq "0" "0" "errors.log field 1 is an ISO-8601 UTC timestamp" ;;
*)
	assert_eq "an ISO-8601 UTC timestamp" "$LINE" "errors.log field 1 is an ISO-8601 UTC timestamp" ;;
esac

# A detail carrying a newline or a pipe must not forge extra lines or fields.
continuity_log "write-decisions" "write-failed" "two|parts
and a second line"
assert_eq "2" "$(wc -l <"$CONTINUITY_DIR/errors.log" | tr -d ' ')" \
	"continuity_log flattens newlines in the detail to keep one line per entry"
assert_eq "4" "$(tail -1 "$CONTINUITY_DIR/errors.log" | tr '|' '\n' | wc -l | tr -d ' ')" \
	"continuity_log flattens pipes in the detail to keep four fields"

# Logging into a store that does not exist is swallowed, never fatal.
CONTINUITY_DIR="$FIXTURE/absent/.continuity"
LOG_STDERR=$(continuity_log "session-start-load" "missing" "no store" 2>&1 >/dev/null)
LOG_RC=$?
assert_ok "$LOG_RC" "continuity_log no-ops when the store is absent"
assert_eq "" "$LOG_STDERR" \
	"continuity_log stays silent when the store is absent — a hook's stderr is not Continuity's to pollute"

# --- continuity_config: defaults, parsed values, malformed values ----------
CONTINUITY_DIR=$(continuity_dir "$FIXTURE")
assert_eq "60" "$(continuity_config retention_days)" \
	"retention_days defaults to 60 with no metadata.json"
assert_eq "true" "$(continuity_config git_tracked)" \
	"git_tracked defaults to true with no metadata.json"

cat >"$CONTINUITY_DIR/metadata.json" <<'JSON'
{
  "schema_version": "1.0",
  "plugin_version": "0.1.0",
  "created_at": "2026-09-12T00:00:00Z",
  "retention_days": 14,
  "git_tracked": false
}
JSON
assert_eq "14" "$(continuity_config retention_days)" \
	"retention_days is read from metadata.json"
assert_eq "false" "$(continuity_config git_tracked)" \
	"git_tracked is read from metadata.json"

printf '%s\n' 'not json at all { "retention_days": maybe,' >"$CONTINUITY_DIR/metadata.json"
assert_eq "60" "$(continuity_config retention_days)" \
	"retention_days falls back to 60 when the value does not parse"
assert_eq "true" "$(continuity_config git_tracked)" \
	"git_tracked falls back to true when the key is absent"

continuity_config no_such_key >/dev/null 2>&1
assert_eq "1" "$?" "continuity_config rejects an unknown key"

exit "${TESTS_FAILED:-0}"
