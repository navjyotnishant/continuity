#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Regex gate rejecting secret-shaped lines before they are persisted (research.md R5).
#
# Sourced, not executed. Targets bash 3.2 (macOS stock) — no associative
# arrays, no ${var,,}. Uses only grep from coreutils/BSD userland.
#
# This is a mitigation, not a guarantee (plan.md Risks): it catches the
# common shapes, and deliberately errs toward blocking. Known false
# positive: a bare 40-character git commit SHA matches the high-entropy
# pattern, so a line quoting one is dropped. Blocking a line about a commit
# costs a note; letting a 32-hex API token into shared git history does not
# come back.

# secret_scan_line <text>
#
# Prints the matched pattern name on stdout and returns 1 when the text
# looks like it carries a credential; prints nothing and returns 0 for
# ordinary text. The caller decides what to do with the line and logs the
# pattern name only — never the matched text (research.md R5).
# AWS-style access key ID: a known 4-character prefix + 16 uppercase
# alphanumerics.
_secret_scan_pattern_aws='(AKIA|ASIA|ABIA|ACCA|AGPA|AIDA|AIPA|ANPA|ANVA|AROA)[A-Z0-9]{16}'

# PEM private-key header, including the labelled variants
# (RSA / EC / OPENSSH / ENCRYPTED). Whitespace between every pair of words is
# one-or-more, not exactly one: a header re-flowed by an editor or pasted
# through a formatter is still a private key.
_secret_scan_pattern_pem='-----BEGIN[[:space:]]+([A-Z0-9]+[[:space:]]+)*PRIVATE[[:space:]]+KEY-----'

# key/token/secret/password assignment: the keyword not preceded by another
# letter or digit (so "monkey=" does not match, while "api_token=" does),
# optional suffix, then : or = and a value of at least 8 credential-shaped
# characters. Matched case-insensitively.
_secret_scan_pattern_cred='(^|[^a-z0-9])(api[-_]?key|key|token|secret|passwd|password)[a-z0-9_-]*[[:space:]]*[:=][[:space:]]*["'"'"']?[a-z0-9/+=_.-]{8,}'

# Long unbroken high-entropy run: 32+ hex, or 40+ base64. Ordinary prose does
# not produce either — words are shorter and separated by spaces.
_secret_scan_pattern_entropy='[0-9a-fA-F]{32,}|[A-Za-z0-9+/]{40,}={0,2}'

secret_scan_line() {
    local text=$1
    local name pattern flags off
    local best_name='' best_off=''

    # Every pattern is tried, and the one whose match starts EARLIEST in the
    # line is the one reported — a line carrying two different secret shapes
    # is named by whichever the reader meets first, not by an evaluation
    # order that is invisible from the outside. Ties keep the order below.
    for name in aws-access-key pem-private-key credential-assignment high-entropy-string; do
        flags=''
        case $name in
            aws-access-key)        pattern=$_secret_scan_pattern_aws ;;
            pem-private-key)       pattern=$_secret_scan_pattern_pem ;;
            credential-assignment) pattern=$_secret_scan_pattern_cred; flags='-i' ;;
            high-entropy-string)   pattern=$_secret_scan_pattern_entropy ;;
        esac

        # grep -bo prints "<byte-offset>:<match>" per match; the first line is
        # the leftmost one. $flags is deliberately unquoted so an empty value
        # expands to no argument at all (bash 3.2 has no nameref to do better).
        # The trailing `|| off=''` keeps a no-match (and a caller running under
        # `set -e -o pipefail`) from aborting the whole hook.
        off=$(printf '%s\n' "$text" | grep -Eob $flags -- "$pattern" 2>/dev/null | head -n 1 | cut -d: -f1) || off=''
        [ -n "$off" ] || continue

        if [ -z "$best_off" ] || [ "$off" -lt "$best_off" ]; then
            best_off=$off
            best_name=$name
        fi

        # Nothing can start earlier than the start of the line.
        if [ "$best_off" -eq 0 ]; then
            break
        fi
    done

    [ -n "$best_name" ] || return 0

    printf '%s\n' "$best_name"
    return 1
}
