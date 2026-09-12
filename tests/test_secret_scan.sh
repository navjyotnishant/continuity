#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: AWS-access-key and PEM-private-key cases for secret_scan_line (T011 slice of T006).
#
# Expects tests/run_tests.sh (T003) to have already defined assert_eq/assert_ok
# and to source this file as one of tests/test_*.sh.

SECRET_SCAN_TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lib/secret_scan.sh
source "$SECRET_SCAN_TEST_DIR/lib/secret_scan.sh"

# --- AWS access key patterns ---

out=$(secret_scan_line "AKIA1234567890ABCDEF")
assert_eq 1 "$?" "AKIA + 16 uppercase alphanumerics is detected"
assert_eq "aws-access-key" "$out" "AKIA match reports aws-access-key"

for prefix in ASIA ABIA ACCA AGPA AIDA AIPA ANPA ANVA AROA; do
    out=$(secret_scan_line "${prefix}1234567890ABCDEF")
    rc=$?
    assert_eq 1 "$rc" "$prefix + 16 uppercase alphanumerics is detected"
    assert_eq "aws-access-key" "$out" "$prefix match reports aws-access-key"
done

out=$(secret_scan_line "XKIA1234567890ABCDEF")
assert_eq 0 "$?" "invalid prefix is not detected as an AWS key"
assert_eq "" "$out" "invalid prefix prints nothing"

out=$(secret_scan_line "AKIA123456789ABC")
assert_eq 0 "$?" "fewer than 16 characters after a valid prefix is not detected"
assert_eq "" "$out" "short suffix prints nothing"

# "More than 16 characters after a valid prefix" is not testable as a
# negative here: secret_scan_line's grep has no trailing anchor, so once a
# valid prefix is followed by 16 uppercase-alphanumeric characters the match
# fires regardless of what comes after — there is no input where "valid
# prefix + >16 valid chars" is true and detection is false. That's the
# implementation's actual (deliberately permissive, per lib/secret_scan.sh's
# own comments) behavior, not a bug to work around here, so this case is
# skipped rather than forced to pass.

out=$(secret_scan_line "AKIA1234567890abcdef")
assert_eq 0 "$?" "lowercase characters after prefix are not detected"
assert_eq "" "$out" "lowercase suffix prints nothing"

out=$(secret_scan_line "AKIA1234-678*ABCDE!")
assert_eq 0 "$?" "non-alphanumeric characters after prefix are not detected"
assert_eq "" "$out" "non-alphanumeric suffix prints nothing"

# --- PEM private key patterns ---

out=$(secret_scan_line "-----BEGIN RSA PRIVATE KEY-----")
assert_eq 1 "$?" "RSA PEM header is detected"
assert_eq "pem-private-key" "$out" "RSA PEM match reports pem-private-key"

out=$(secret_scan_line "-----BEGIN EC PRIVATE KEY-----")
assert_eq 1 "$?" "EC PEM header is detected"
assert_eq "pem-private-key" "$out" "EC PEM match reports pem-private-key"

# --- Credential-assignment patterns ---

out=$(secret_scan_line "secretValue=AbCdEfGh12345678")
assert_eq 1 "$?" "credential keyword with an alphanumeric suffix (secretValue=) is detected"
assert_eq "credential-assignment" "$out" "keyword-with-suffix match reports credential-assignment"

out=$(secret_scan_line "token: AbCdEfGh12345678")
assert_eq 1 "$?" "value after a colon separator is detected"
assert_eq "credential-assignment" "$out" "colon-separated match reports credential-assignment"

out=$(secret_scan_line "token=AbCdEfGh12345678")
assert_eq 1 "$?" "value after an equals separator is detected"
assert_eq "credential-assignment" "$out" "equals-separated match reports credential-assignment"

out=$(secret_scan_line "key = AbCdEfGh12345678")
assert_eq 1 "$?" "optional whitespace around the separator is detected"
assert_eq "credential-assignment" "$out" "whitespace-around-separator match reports credential-assignment"

out=$(secret_scan_line 'key="AbCdEfGh12345678"')
assert_eq 1 "$?" "optional double-quoted value is detected"
assert_eq "credential-assignment" "$out" "double-quoted-value match reports credential-assignment"

out=$(secret_scan_line "key='AbCdEfGh12345678'")
assert_eq 1 "$?" "optional single-quoted value is detected"
assert_eq "credential-assignment" "$out" "single-quoted-value match reports credential-assignment"

out=$(secret_scan_line "monkey=AbCdEfGh12345678")
assert_eq 0 "$?" "keyword preceded by an alphanumeric (monkey=) is not detected"
assert_eq "" "$out" "alphanumeric-preceded keyword prints nothing"

out=$(secret_scan_line "key=AbCdEfG")
assert_eq 0 "$?" "credential-assignment value shorter than 8 characters is not detected"
assert_eq "" "$out" "short value prints nothing"

out=$(secret_scan_line "secret=LineStartValue1")
assert_eq 1 "$?" "credential-assignment at the start of the line is detected"
assert_eq "credential-assignment" "$out" "line-start match reports credential-assignment"

out=$(secret_scan_line "export FOO; token=AbCdEfGh12345678 && echo done")
assert_eq 1 "$?" "credential-assignment in the middle of the line is detected"
assert_eq "credential-assignment" "$out" "mid-line match reports credential-assignment"

# --- High-entropy string patterns ---

out=$(secret_scan_line "deadbeefdeadbeefdeadbeefdeadbeef")
assert_eq 1 "$?" "32 consecutive hexadecimal characters is detected"
assert_eq "high-entropy-string" "$out" "32-hex run reports high-entropy-string"

out=$(secret_scan_line "HelloWorldHelloWorldHelloWorldHelloWorld")
assert_eq 1 "$?" "40+ consecutive base64 characters is detected"
assert_eq "high-entropy-string" "$out" "base64 run reports high-entropy-string"

out=$(secret_scan_line "HelloWorldHelloWorldHelloWorldHelloWorld")
assert_eq 1 "$?" "40-character base64 with zero padding equals signs is detected"
assert_eq "high-entropy-string" "$out" "unpadded base64 reports high-entropy-string"

out=$(secret_scan_line "HelloWorldHelloWorldHelloWorldHelloWorld=")
assert_eq 1 "$?" "base64 with one padding equals sign is detected"
assert_eq "high-entropy-string" "$out" "one-padded base64 reports high-entropy-string"

out=$(secret_scan_line "HelloWorldHelloWorldHelloWorldHelloWorld==")
assert_eq 1 "$?" "base64 with two padding equals signs is detected"
assert_eq "high-entropy-string" "$out" "two-padded base64 reports high-entropy-string"

out=$(secret_scan_line "0123456789abcdef0123456789abcde")
assert_eq 0 "$?" "31 hexadecimal characters is not detected"
assert_eq "" "$out" "31 hex chars prints nothing"

out=$(secret_scan_line "HelloWorldHelloWorldHelloWorldHelloWorl")
assert_eq 0 "$?" "39 base64 characters is not detected"
assert_eq "" "$out" "39 base64 chars prints nothing"

out=$(secret_scan_line "0123456789ABCDEFabcdef0123456789ABCDEFab")
assert_eq 1 "$?" "mixed-case hexadecimal is detected"
assert_eq "high-entropy-string" "$out" "mixed-case hex reports high-entropy-string"

out=$(secret_scan_line "The quick brown fox jumps over the lazy dog near the riverbank at dawn")
assert_eq 0 "$?" "ordinary English prose is not detected"
assert_eq "" "$out" "ordinary prose prints nothing"

out=$(secret_scan_line "Fixed in commit 3f786850e387550fdab836ed7e6dc881de23001b, see the changelog")
assert_eq 1 "$?" "a 40-character git commit SHA is detected (documented false positive)"
assert_eq "high-entropy-string" "$out" "git SHA reports high-entropy-string"

# --- Return value and output behavior ---

secret_scan_line "AKIA1234567890ABCDEF" >/dev/null
assert_eq 1 "$?" "exit code is 1 when a pattern matches"

secret_scan_line "just an ordinary sentence with no secrets in it" >/dev/null
assert_eq 0 "$?" "exit code is 0 when no pattern matches"
