#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Output-behavior and edge-case cases for secret_scan_line (T006 slice: return
#   value/output behavior + empty/long/multi-pattern/special-char edge cases).
#
# Expects tests/run_tests.sh (T003) to have already defined assert_eq/assert_ok
# and to source this file as one of tests/test_*.sh.

SECRET_SCAN_TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lib/secret_scan.sh
source "$SECRET_SCAN_TEST_DIR/lib/secret_scan.sh"

# --- Return value and output behavior ---

out=$(secret_scan_line "AKIA1234567890ABCDEF")
assert_eq "aws-access-key" "$out" "matched pattern name aws-access-key is printed to stdout"

out=$(secret_scan_line "-----BEGIN RSA PRIVATE KEY-----")
assert_eq "pem-private-key" "$out" "matched pattern name pem-private-key is printed to stdout"

out=$(secret_scan_line "api_token: abcd1234efgh5678")
assert_eq "credential-assignment" "$out" "matched pattern name credential-assignment is printed to stdout"

out=$(secret_scan_line "0123456789ABCDEFabcdef0123456789ABCDEFab")
assert_eq "high-entropy-string" "$out" "matched pattern name high-entropy-string is printed to stdout"

out=$(secret_scan_line "just an ordinary sentence with no secrets in it")
assert_eq "" "$out" "prints nothing to stdout on non-match"

secret=aC7hK9mN2pQ4rS6t
out=$(secret_scan_line "password=${secret}extra")
if printf '%s' "$out" | grep -qF "$secret"; then
    echo "FAIL: matched secret text leaked to stdout: $out"
    exit 1
fi
assert_eq "credential-assignment" "$out" "output on match is only the pattern name, never the secret text"

# --- Edge cases ---

out=$(secret_scan_line "")
rc=$?
assert_eq 0 "$rc" "empty string input returns 0"
assert_eq "" "$out" "empty string input prints nothing"

out=$(secret_scan_line "   ")
rc=$?
assert_eq 0 "$rc" "whitespace-only input returns 0"
assert_eq "" "$out" "whitespace-only input prints nothing"

out=$(secret_scan_line "-----BEGIN RSA PRIVATE KEY----- AKIA1234567890ABCDEF")
rc=$?
assert_eq 1 "$rc" "input matching multiple patterns still returns 1"
assert_eq "aws-access-key" "$out" "input matching multiple patterns detects only the first one checked"

long_prose=""
i=0
while [ "$i" -lt 500 ]; do
    long_prose="${long_prose}the quick brown fox jumps over the lazy dog "
    i=$((i + 1))
done
out=$(secret_scan_line "$long_prose")
rc=$?
assert_eq 0 "$rc" "very long non-credential input returns 0"
assert_eq "" "$out" "very long non-credential input prints nothing"

long_secret="password=abcd1234efgh5678ijkl"
i=0
while [ "$i" -lt 200 ]; do
    long_secret="filler text ${long_secret}"
    i=$((i + 1))
done
out=$(secret_scan_line "$long_secret")
rc=$?
assert_eq 1 "$rc" "very long input containing a credential is still detected"
assert_eq "credential-assignment" "$out" "very long input reports the matched pattern name"

out=$(secret_scan_line '!@#$%^&*()_+-={}[]|\:;"<>,.?/~\`')
rc=$?
assert_eq 0 "$rc" "special characters in non-credential context return 0"
assert_eq "" "$out" "special characters in non-credential context print nothing"

out=$(secret_scan_line "api_key=abcd1234efgh5678 -----BEGIN RSA PRIVATE KEY-----")
rc=$?
assert_eq 1 "$rc" "input matching credential-assignment and pem-private-key still returns 1"
assert_eq "credential-assignment" "$out" "first matching pattern (credential-assignment) is reported, not pem-private-key"
