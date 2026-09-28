#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Shared Continuity helpers — resolve a project's .continuity/
#              store, append a failure line to errors.log, and read the
#              user-editable config out of metadata.json.
#
# Sourced, never executed. POSIX-compatible bash (targets bash 3.2, macOS's
# stock version) plus coreutils only — plan.md forbids any other runtime.
#
# continuity_log and continuity_config act on $CONTINUITY_DIR, which a caller
# sets once per run (typically `CONTINUITY_DIR=$(continuity_dir "$cwd")` from
# the hook's JSON `cwd`). They fall back to resolving it from $PWD so a helper
# invoked outside a hook still writes to the right store rather than nowhere.

# Defaults per data-model.md → metadata.json. Used whenever metadata.json is
# absent, unreadable, or does not parse.
CONTINUITY_DEFAULT_RETENTION_DAYS=60
CONTINUITY_DEFAULT_GIT_TRACKED=true

# continuity_dir <cwd> — print the path of <cwd>'s .continuity/ store.
#
# Pure path computation: the store frequently does not exist yet, and absence
# is not an error here (hook-io-contract.md → SessionStart exits quietly when
# the store is missing). The hook contract defines `cwd` as the absolute
# project path, and Q10 scopes the MVP to a single project root, so there is
# no upward walk for a git root.
continuity_dir() {
	[ -n "$1" ] || return 1
	printf '%s\n' "${1%/}/.continuity"
}

# continuity_log <operation> <failure-kind> <detail> — append one failure line
# to $CONTINUITY_DIR/errors.log in file-format-contract.md's pipe-delimited
# shape: `<ISO-8601 UTC timestamp> | <operation> | <failure-kind> | <detail>`.
#
# The caller is responsible for <detail> carrying no file, conversation, or
# credential content (data-model.md). What this function guarantees is the
# line shape: a newline or pipe in <detail> would forge extra lines or fields
# that a reader would then silently skip, so both are flattened to spaces.
#
# Always returns 0. A failure to log is the one failure Continuity does not
# log — doing so would recurse — so it is swallowed (data-model.md → Failure
# Log Entry validation rules).
continuity_log() {
	local dir ts detail
	dir="${CONTINUITY_DIR:-$(continuity_dir "$PWD")}"
	ts=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null) || return 0
	detail=$(printf '%s' "$3" | tr '\n|' '  ')
	# The redirection is inside the group so that the shell's own "No such
	# file or directory" for an absent store is swallowed too — 2>/dev/null on
	# the printf alone would still let that one through.
	{ printf '%s | %s | %s | %s\n' "$ts" "$1" "$2" "$detail" \
		>>"$dir/errors.log"; } 2>/dev/null || return 0
	return 0
}

# continuity_config <key> — print `retention_days` or `git_tracked` from
# $CONTINUITY_DIR/metadata.json, falling back to the documented default when
# the file is absent, unreadable, or the value does not parse. Returns
# non-zero only for an unknown key.
#
# Read fresh on every call rather than cached: data-model.md requires a
# mid-session hand-edit of metadata.json to take effect without a restart.
# Parsed with grep/sed because jq is not guaranteed present and plan.md
# permits no dependency beyond coreutils; the file is a flat object written by
# this plugin, so a full JSON parser would buy nothing a malformed value does
# not already fall back from.
continuity_config() {
	local key dir file raw value
	key="$1"
	case "$key" in
	retention_days) value="$CONTINUITY_DEFAULT_RETENTION_DAYS" ;;
	git_tracked) value="$CONTINUITY_DEFAULT_GIT_TRACKED" ;;
	*) return 1 ;;
	esac

	dir="${CONTINUITY_DIR:-$(continuity_dir "$PWD")}"
	file="$dir/metadata.json"
	raw=""
	if [ -r "$file" ]; then
		raw=$(grep -o "\"$key\"[[:space:]]*:[[:space:]]*[^,}[:space:]]*" "$file" 2>/dev/null |
			head -1 | sed 's/.*:[[:space:]]*//')
	fi

	case "$key" in
	retention_days)
		# Digits only; a quoted, negative, or absent value keeps the default.
		case "$raw" in
		'' | *[!0-9]*) ;;
		*) value="$raw" ;;
		esac
		;;
	git_tracked)
		case "$raw" in
		true | false) value="$raw" ;;
		esac
		;;
	esac

	printf '%s\n' "$value"
}
