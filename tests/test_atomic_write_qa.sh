#!/usr/bin/env bash
# Author: Navjyot Nishant
# Created: 2026-09-12
# Last updated: 2026-09-12
# Description: Independent QA suite for lib/atomic_write.sh (T004, CONTINUI-27).
#
# Self-contained: does not depend on tests/test_atomic_write.sh or any shared
# harness (tests/run_tests.sh / T003 does not exist on this branch, and the
# existing tests/test_atomic_write.sh never invokes the test functions it
# defines, so it currently verifies nothing when run). Written independently
# from the diff and the ticket's acceptance criteria, not from the
# implementer's test file.
#
# Run: bash tests/test_atomic_write_qa.sh
# Exit: 0 if every case passes, 1 otherwise. Prints PASS/FAIL per case.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
. "$SCRIPT_DIR/../lib/atomic_write.sh"

pass_count=0
fail_count=0

report() {
    # report <ok:0|1> <case description>
    if [ "$1" -eq 0 ]; then
        pass_count=$((pass_count + 1))
        printf 'PASS: %s\n' "$2"
    else
        fail_count=$((fail_count + 1))
        printf 'FAIL: %s\n' "$2"
    fi
}

eq() {
    # eq <expected> <actual> <case description>
    if [ "$1" = "$2" ]; then
        report 0 "$3"
    else
        fail_count=$((fail_count + 1))
        printf 'FAIL: %s (expected %s, got %s)\n' "$3" "$(printf '%q' "$1")" "$(printf '%q' "$2")"
    fi
}

t_dir() { mktemp -d "${TMPDIR:-/tmp}/atomic_write_qa.XXXXXX"; }

# 1. Successful write with explicit content argument
tmpdir=$(t_dir); target="$tmpdir/target.txt"
atomic_write "$target" "hello world"
eq "hello world" "$(cat "$target" 2>/dev/null)" "explicit-content write persists content"
rm -rf "$tmpdir"

# 2. Successful write from stdin
tmpdir=$(t_dir); target="$tmpdir/target.txt"
echo "from stdin" | atomic_write "$target"
eq "from stdin" "$(cat "$target" 2>/dev/null)" "stdin write persists content"
rm -rf "$tmpdir"

# 3. Successful write returns exit code 0
tmpdir=$(t_dir); target="$tmpdir/target.txt"
atomic_write "$target" "content"
eq "0" "$?" "successful write returns exit code 0"
rm -rf "$tmpdir"

# 4. Failed write returns non-zero exit code
tmpdir=$(t_dir); target="$tmpdir/no-such-dir/target.txt"
atomic_write "$target" "content"
rc=$?
report "$([ "$rc" -ne 0 ]; echo $?)" "failed write returns non-zero exit code"
rm -rf "$tmpdir"

# 5. Empty string argument is rejected and returns non-zero
tmpdir=$(t_dir); target="$tmpdir/target.txt"
atomic_write "$target" ""
rc=$?
report "$([ "$rc" -ne 0 ]; echo $?)" "empty string argument is rejected"
rm -rf "$tmpdir"

# 6. Empty stdin input is rejected and returns non-zero
tmpdir=$(t_dir); target="$tmpdir/target.txt"
printf '' | atomic_write "$target"
rc=$?
report "$([ "$rc" -ne 0 ]; echo $?)" "empty stdin input is rejected"
rm -rf "$tmpdir"

# 7. Whitespace-only content (spaces) is rejected
tmpdir=$(t_dir); target="$tmpdir/target.txt"
atomic_write "$target" "   "
rc=$?
report "$([ "$rc" -ne 0 ]; echo $?)" "whitespace-only content (spaces) is rejected"
rm -rf "$tmpdir"

# 8. Whitespace-only content (newline only) is rejected
tmpdir=$(t_dir); target="$tmpdir/target.txt"
atomic_write "$target" "
"
rc=$?
report "$([ "$rc" -ne 0 ]; echo $?)" "whitespace-only content (newline only) is rejected"
rm -rf "$tmpdir"

# 9. Whitespace-only content (tabs only) is rejected
tmpdir=$(t_dir); target="$tmpdir/target.txt"
atomic_write "$target" "$(printf '\t\t\t')"
rc=$?
report "$([ "$rc" -ne 0 ]; echo $?)" "whitespace-only content (tabs only) is rejected"
rm -rf "$tmpdir"

# 10. Whitespace-only content (mixed spaces/tabs/newlines) is rejected
tmpdir=$(t_dir); target="$tmpdir/target.txt"
atomic_write "$target" "$(printf ' \t\n \t\n')"
rc=$?
report "$([ "$rc" -ne 0 ]; echo $?)" "whitespace-only content (mixed spaces/tabs/newlines) is rejected"
rm -rf "$tmpdir"

# 11. Target file is not modified when write is rejected for empty content
tmpdir=$(t_dir); target="$tmpdir/target.txt"
printf '%s\n' "original" > "$target"
atomic_write "$target" ""
eq "original" "$(cat "$target")" "target file is not modified when write is rejected for empty content"
rm -rf "$tmpdir"

# 12. Target file is not created when write is rejected for empty content
tmpdir=$(t_dir); target="$tmpdir/target.txt"
atomic_write "$target" ""
eq "false" "$([ -e "$target" ] && echo true || echo false)" "target file is not created when write is rejected for empty content"
rm -rf "$tmpdir"

# 13. Content with embedded whitespace but non-whitespace boundary is accepted
tmpdir=$(t_dir); target="$tmpdir/target.txt"
atomic_write "$target" "hello   world"
rc=$?
eq "0" "$rc" "content with embedded whitespace but non-whitespace boundary is accepted (exit code)"
eq "hello   world" "$(cat "$target")" "content with embedded whitespace persists unchanged"
rm -rf "$tmpdir"

# 14. Temp file is created with target path plus .tmp. plus the process PID
tmpdir=$(t_dir); target="$tmpdir/target.txt"
captured=""
mv() { captured="$2"; command mv "$@"; }
atomic_write "$target" "content"
unset -f mv
eq "${target}.tmp.$$" "$captured" "temp file is target path plus .tmp. plus the process PID"
rm -rf "$tmpdir"

# 15. Temp file is created in the same directory as the target file
tmpdir=$(t_dir); target="$tmpdir/target.txt"
captured=""
mv() { captured="$(dirname "$2")"; command mv "$@"; }
atomic_write "$target" "content"
unset -f mv
eq "$tmpdir" "$captured" "temp file is created in the same directory as the target file"
rm -rf "$tmpdir"

# 16. Temp file is removed if write fails (permission denied on directory)
if [ "$(id -u)" -ne 0 ]; then
    tmpdir=$(t_dir); chmod 555 "$tmpdir"; target="$tmpdir/target.txt"
    atomic_write "$target" "content"
    rc=$?
    report "$([ "$rc" -ne 0 ]; echo $?)" "write into a non-writable directory returns non-zero"
    leftover=$(find "$tmpdir" -maxdepth 1 -name "target.txt.tmp.*" 2>/dev/null)
    eq "" "$leftover" "temp file is removed when write fails on a non-writable directory"
    chmod 755 "$tmpdir"; rm -rf "$tmpdir"
else
    printf 'SKIP: write-failure temp cleanup case (running as root, permissions not enforced)\n'
fi

# 17. Temp file is removed if rename fails
tmpdir=$(t_dir); target="$tmpdir/target.txt"
echo "original" > "$target"
locked=0
if command -v chflags >/dev/null 2>&1; then
    chflags uchg "$target" && locked=1
elif command -v chattr >/dev/null 2>&1; then
    chattr +i "$target" 2>/dev/null && locked=1
fi
if [ "$locked" -eq 1 ]; then
    atomic_write "$target" "new content"
    rc=$?
    report "$([ "$rc" -ne 0 ]; echo $?)" "rename onto an immutable target returns non-zero"
    leftover=$(find "$tmpdir" -maxdepth 1 -name "target.txt.tmp.*" 2>/dev/null)
    eq "" "$leftover" "temp file is removed when rename fails"
    if command -v chflags >/dev/null 2>&1; then
        chflags nouchg "$target"
    elif command -v chattr >/dev/null 2>&1; then
        chattr -i "$target" 2>/dev/null
    fi
else
    printf 'SKIP: rename-failure temp cleanup case (no chflags/chattr available to lock the target)\n'
fi
rm -rf "$tmpdir"

# 18. Overwriting an existing target file replaces it atomically
tmpdir=$(t_dir); target="$tmpdir/target.txt"
echo "original content" > "$target"
atomic_write "$target" "replacement content"
rc=$?
eq "0" "$rc" "overwrite of an existing target returns 0"
eq "replacement content" "$(cat "$target")" "existing target is fully replaced, not appended to"
rm -rf "$tmpdir"

# 19. Content with leading non-whitespace is accepted even if trailing whitespace follows
tmpdir=$(t_dir); target="$tmpdir/target.txt"
atomic_write "$target" "hello   "
rc=$?
eq "0" "$rc" "leading non-whitespace content is accepted despite trailing whitespace"
eq "hello   " "$(cat "$target")" "trailing whitespace after real content is preserved, not stripped"
rm -rf "$tmpdir"

# 20. Content from stdin is preferred when both argument and stdin are provided
# (argument takes precedence per the implementation's contract)
tmpdir=$(t_dir); target="$tmpdir/target.txt"
echo "from stdin" | atomic_write "$target" "from argument"
eq "from argument" "$(cat "$target")" "argument content wins over stdin when both are given"
rm -rf "$tmpdir"

# 21. Newline is added to end of written content
tmpdir=$(t_dir); target="$tmpdir/target.txt"
atomic_write "$target" "no newline here"
last_line=$(sed -n '$p' "$target")
line_count=$(wc -l < "$target" | tr -d ' ')
eq "no newline here" "$last_line" "trailing newline is appended to written content (content line)"
eq "1" "$line_count" "trailing newline is appended to written content (line count)"
rm -rf "$tmpdir"

# 22. Write to a path with special characters (spaces, quotes, etc.) succeeds
tmpdir=$(t_dir); target="$tmpdir/has space 'quote' \$dollar.txt"
atomic_write "$target" "content"
rc=$?
eq "0" "$rc" "write to a path with spaces and quotes succeeds"
eq "content" "$(cat "$target" 2>/dev/null)" "content persists at the special-character path"
rm -rf "$tmpdir"

# 23. Write in a subdirectory succeeds if parent directory exists
tmpdir=$(t_dir); mkdir -p "$tmpdir/subdir"; target="$tmpdir/subdir/target.txt"
atomic_write "$target" "content"
rc=$?
eq "0" "$rc" "write into an existing subdirectory succeeds"
rm -rf "$tmpdir"

# 24. Write fails non-zero if target directory does not exist
tmpdir=$(t_dir); target="$tmpdir/does-not-exist/target.txt"
atomic_write "$target" "content"
rc=$?
report "$([ "$rc" -ne 0 ]; echo $?)" "write fails non-zero when target directory does not exist"
eq "false" "$([ -e "$target" ] && echo true || echo false)" "no file is created when target directory is missing"
rm -rf "$tmpdir"

# 25. Multiple values passed beyond two arguments are handled without error
tmpdir=$(t_dir); target="$tmpdir/target.txt"
atomic_write "$target" "content" "extra1" "extra2" "extra3"
rc=$?
eq "0" "$rc" "extra arguments beyond target and content do not cause an error"
eq "content" "$(cat "$target")" "only the second argument is used as content when extra arguments are passed"
rm -rf "$tmpdir"

printf '\n%d passed, %d failed\n' "$pass_count" "$fail_count"
[ "$fail_count" -eq 0 ]
