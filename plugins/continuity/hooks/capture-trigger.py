"""hooks/capture-trigger.py — PostToolUse hook (T019).

Classifies whether the tool call that just ran is a meaningful-change signal
(contracts/hook-io-contract.md -> PostToolUse) and, if so, launches
lib/write_memory.py detached and exits. It never waits for the writer, never
takes the store lock, and never writes a file itself — that is what keeps the
interactive turn that triggered it unaffected (FR-010).

A non-meaningful signal is a legitimate no-op: no output, no write, and
nothing logged (FR-011). A whitespace-only edit is the spec's own documented
example.

CONTINUI-47: the target project is the edited file's own repository, not the
session's `cwd`. A session can run with its `cwd` in one repo while a tool
call edits a file that lives in another (this codebase's own working
directories, for instance, span several repos at once) — resolving from
`cwd` alone wrote every note into the session's repo regardless of which
project the change actually belonged to. `Edit`/`Write`/`MultiEdit` carry the
edited file's path in `tool_input.file_path`; the `Bash` git-diff trigger has
no single edited file, so it still resolves from `cwd`, which is exactly the
repo the git command itself ran against.

Codex and Cursor payloads are converted to this shape by `lib/agents.py`
first; a Codex patch naming several files yields one writer per distinct
repository.

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


def project_root_for(payload):
    """Return the target project root: the edited file's own repo, or `cwd`.

    Walks up from `tool_input.file_path`'s directory to the nearest `.git`
    (file or directory — a worktree's `.git` is a file). Falls back to
    `cwd` when there is no file_path (the Bash trigger) or no `.git` is
    found above it (an untracked file, or file_path missing/relative in a
    payload shape this hook does not otherwise handle).
    """
    cwd = payload.get("cwd")
    file_path = (payload.get("tool_input") or {}).get("file_path")
    if not isinstance(file_path, str) or not file_path or not os.path.isabs(file_path):
        return cwd

    directory = os.path.dirname(file_path)
    while directory and directory != os.path.dirname(directory):
        if os.path.exists(os.path.join(directory, ".git")):
            return directory
        directory = os.path.dirname(directory)
    return cwd


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

    try:
        sys.path.insert(0, PLUGIN_ROOT)
        from lib import agents

        payloads = agents.normalize(parsed, os.environ)
    except Exception:  # fail open; never raise out of a hook (agents.py may
        # be absent from a partial/fake plugin install) — treat the payload
        # as already Claude-shaped, same as agents.normalize does for Claude.
        payloads = [parsed]

    launches = []
    for payload in payloads:
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            continue
        try:
            trigger_kind = classify(payload)
        except Exception:
            trigger_kind = None
        if not trigger_kind:
            continue
        target = project_root_for(payload)
        target = target if isinstance(target, str) and target else cwd
        if (target, trigger_kind) not in launches:
            launches.append((target, trigger_kind))

    for target, trigger_kind in launches:
        launch_writer(target, trigger_kind)
    return 0


if __name__ == "__main__":
    sys.exit(main())
