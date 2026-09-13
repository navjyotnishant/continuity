"""hooks/capture-trigger.py — PostToolUse hook (T019).

Classifies whether the tool call that just ran is a meaningful-change signal
(contracts/hook-io-contract.md -> PostToolUse) and, if so, launches
lib/write_memory.py detached and exits. It never waits for the writer, never
takes the store lock, and never writes a file itself — that is what keeps the
interactive turn that triggered it unaffected (FR-010).

A non-meaningful signal is a legitimate no-op: no output, no write, and
nothing logged (FR-011). A whitespace-only edit is the spec's own documented
example.

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import json
import os
import subprocess
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRITER = os.path.join(PLUGIN_ROOT, "lib", "write_memory.py")

EDIT_TOOLS = ("Edit", "Write", "MultiEdit")
GIT_DIFF_TIMEOUT = 5


def classify(payload):
    """Return the trigger kind for this tool call, or None if it is a no-op."""
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    if tool_name in EDIT_TOOLS:
        return "file-change" if _is_meaningful_edit(tool_name, tool_input) else None

    if tool_name == "Bash":
        command = tool_input.get("command") or ""
        if "git" not in command:
            return None
        if "git commit" in command:
            return "git-diff"
        return "git-diff" if _has_non_whitespace_diff(payload.get("cwd")) else None

    return None


def _is_meaningful_edit(tool_name, tool_input):
    """True unless the edit provably changed nothing but whitespace.

    Defaults to True when the payload does not carry enough to tell: an extra
    no-op writer run costs nothing (it finds nothing staged and exits), while
    a missed signal loses a checkpoint.
    """
    if tool_name == "Write":
        content = tool_input.get("content")
        if content is None:
            return True
        return bool(content.strip())

    edits = tool_input.get("edits")
    if isinstance(edits, list) and edits:
        return any(_changes_more_than_whitespace(edit) for edit in edits)

    return _changes_more_than_whitespace(tool_input)


def _changes_more_than_whitespace(edit):
    if not isinstance(edit, dict):
        return True
    old_string = edit.get("old_string")
    new_string = edit.get("new_string")
    if old_string is None or new_string is None:
        return True
    return _squeeze(old_string) != _squeeze(new_string)


def _squeeze(text):
    return "".join(text.split())


def _has_non_whitespace_diff(cwd):
    """True if `git diff -w` reports any change in the project root.

    `-w` is what makes this the "non-whitespace" test the contract asks for:
    a whitespace-only working tree produces empty output.
    """
    if not cwd:
        return False
    for target in (["HEAD"], []):
        try:
            result = subprocess.run(
                ["git", "-C", cwd, "diff", "-w", "--shortstat"] + target,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=GIT_DIFF_TIMEOUT,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        if result.returncode == 0:
            return bool(result.stdout.strip())
    return False


def detach_kwargs():
    """Platform-specific arguments that orphan the writer (research.md R4)."""
    if os.name == "nt":
        return {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
        }
    return {"start_new_session": True}


def launch_writer(cwd, trigger_kind, writer=WRITER):
    """Fire the writer and return immediately. Never raises."""
    try:
        subprocess.Popen(
            [sys.executable or "python3", writer, cwd, trigger_kind],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            **detach_kwargs()
        )
    except (OSError, ValueError):
        _log(cwd, "write-failed", "writer not launched")


def _log(cwd, failure_kind, detail):
    # Imported lazily so the ordinary no-op path stays a bare-stdlib startup.
    sys.path.insert(0, PLUGIN_ROOT)
    from lib.common import continuity_dir, continuity_log

    continuity_log(continuity_dir(cwd), "capture-trigger", failure_kind, detail)


def main():
    try:
        raw = sys.stdin.read()
        parsed = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError):
        return 0

    # Valid JSON that is not an object is as malformed as unparseable bytes:
    # both mean "no signal to classify", and neither may raise out of a hook.
    if not isinstance(parsed, dict):
        return 0

    cwd = parsed.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return 0

    try:
        trigger_kind = classify(parsed)
    except Exception:
        trigger_kind = None

    if trigger_kind:
        launch_writer(cwd, trigger_kind)
    return 0


if __name__ == "__main__":
    sys.exit(main())
