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
secret_scan_line() {
    local text=$1

    # AWS-style access key ID: a known 4-character prefix + 16 uppercase
    # alphanumerics.
    if printf '%s\n' "$text" | grep -Eq '(AKIA|ASIA|ABIA|ACCA|AGPA|AIDA|AIPA|ANPA|ANVA|AROA)[A-Z0-9]{16}'; then
        printf '%s\n' 'aws-access-key'
        return 1
    fi

    # PEM private-key header, including the labelled variants
    # (RSA / EC / OPENSSH / ENCRYPTED). Whitespace between every pair of
    # words is one-or-more, not exactly one: a header re-flowed by an editor
    # or pasted through a formatter is still a private key.
    if printf '%s\n' "$text" | grep -Eq -- '-----BEGIN[[:space:]]+([A-Z0-9]+[[:space:]]+)*PRIVATE[[:space:]]+KEY-----'; then
        printf '%s\n' 'pem-private-key'
        return 1
    fi

    # key/token/secret/password assignment: the keyword not preceded by
    # another letter or digit (so "monkey=" does not match, while
    # "api_token=" does), optional suffix, then : or = and a value of at
    # least 8 credential-shaped characters.
    if printf '%s\n' "$text" | grep -Eqi '(^|[^a-z0-9])(api[-_]?key|key|token|secret|passwd|password)[a-z0-9_-]*[[:space:]]*[:=][[:space:]]*["'"'"']?[a-z0-9/+=_.-]{8,}'; then
        printf '%s\n' 'credential-assignment'
        return 1
    fi

    # Long unbroken high-entropy run: 32+ hex, or 40+ base64. Ordinary prose
    # does not produce either — words are shorter and separated by spaces.
    if printf '%s\n' "$text" | grep -Eq '[0-9a-fA-F]{32,}|[A-Za-z0-9+/]{40,}={0,2}'; then
        printf '%s\n' 'high-entropy-string'
        return 1
    fi

    return 0
}
