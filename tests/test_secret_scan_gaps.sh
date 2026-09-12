#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: QA gap-fill cases for secret_scan_line (T006) not covered by
#   tests/test_secret_scan.sh or tests/test_secret_scan_output.sh: the
#   remaining PEM header variants/negatives and credential-keyword variants
#   from the CONTINUI-29 acceptance criteria.
#
# Expects tests/run_tests.sh to have already defined assert_eq/assert_ok
# and to source this file as one of tests/test_*.sh.

SECRET_SCAN_TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=../lib/secret_scan.sh
source "$SECRET_SCAN_TEST_DIR/lib/secret_scan.sh"

# --- PEM private key patterns: remaining labelled variants ---

out=$(secret_scan_line "-----BEGIN OPENSSH PRIVATE KEY-----")
assert_eq 1 "$?" "OPENSSH PEM header is detected"
assert_eq "pem-private-key" "$out" "OPENSSH PEM match reports pem-private-key"

out=$(secret_scan_line "-----BEGIN ENCRYPTED PRIVATE KEY-----")
assert_eq 1 "$?" "ENCRYPTED PEM header is detected"
assert_eq "pem-private-key" "$out" "ENCRYPTED PEM match reports pem-private-key"

out=$(secret_scan_line "-----BEGIN  RSA PRIVATE KEY-----")
assert_eq 1 "$?" "PEM header with multiple spaces before the type word is detected"
assert_eq "pem-private-key" "$out" "multi-space-before-type-word PEM match reports pem-private-key"

# The acceptance criterion says "multiple spaces between words" without
# qualification. The regex's tail is a literal "PRIVATE KEY" with exactly
# one space, so multiple spaces between PRIVATE and KEY specifically are
# not detected. This assertion documents that gap against the spec as
# written; see QA report.
out=$(secret_scan_line "-----BEGIN RSA PRIVATE  KEY-----")
assert_eq 1 "$?" "PEM header with multiple spaces between PRIVATE and KEY is detected"
assert_eq "pem-private-key" "$out" "multi-space-before-KEY PEM match reports pem-private-key"

# --- PEM private key patterns: negatives ---

out=$(secret_scan_line "-----BEGIN RSA PRIVATE KEY")
assert_eq 0 "$?" "incomplete PEM header missing the trailing ----- is not detected"
assert_eq "" "$out" "incomplete PEM header prints nothing"

out=$(secret_scan_line "-----BEGIN PUBLIC KEY-----")
assert_eq 0 "$?" "PUBLIC KEY header is not detected as a private key"
assert_eq "" "$out" "PUBLIC KEY header prints nothing"

out=$(secret_scan_line "----BEGIN RSA PRIVATE KEY----")
assert_eq 0 "$?" "malformed PEM header (3-dash delimiter instead of 5) is not detected"
assert_eq "" "$out" "malformed PEM header prints nothing"

# --- Credential-assignment patterns: keyword variants from the spec ---

out=$(secret_scan_line "api_key=AbCdEfGh12345678")
assert_eq 1 "$?" "api_key= is detected"
assert_eq "credential-assignment" "$out" "api_key match reports credential-assignment"

out=$(secret_scan_line "apikey=AbCdEfGh12345678")
assert_eq 1 "$?" "apikey= is detected"
assert_eq "credential-assignment" "$out" "apikey match reports credential-assignment"

out=$(secret_scan_line "api-key=AbCdEfGh12345678")
assert_eq 1 "$?" "api-key= is detected"
assert_eq "credential-assignment" "$out" "api-key match reports credential-assignment"

out=$(secret_scan_line "passwd=AbCdEfGh12345678")
assert_eq 1 "$?" "passwd= is detected"
assert_eq "credential-assignment" "$out" "passwd match reports credential-assignment"

out=$(secret_scan_line "password=AbCdEfGh12345678")
assert_eq 1 "$?" "password= is detected"
assert_eq "credential-assignment" "$out" "password match reports credential-assignment"

out=$(secret_scan_line "SECRET=AbCdEfGh12345678")
assert_eq 1 "$?" "uppercase keyword (SECRET=) is detected case-insensitively"
assert_eq "credential-assignment" "$out" "uppercase keyword match reports credential-assignment"

out=$(secret_scan_line "Api_Key=AbCdEfGh12345678")
assert_eq 1 "$?" "mixed-case keyword (Api_Key=) is detected case-insensitively"
assert_eq "credential-assignment" "$out" "mixed-case keyword match reports credential-assignment"
