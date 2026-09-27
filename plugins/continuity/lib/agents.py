"""lib/agents.py — the one module that knows how coding agents differ.

Claude Code, Codex and Cursor call the same hook scripts with different
payloads (specs/002-multi-agent/design.md). normalize() turns any of them into
the Claude Code payload shape the hooks already handle; format_context() turns
recall text into the shape the calling agent reads. Pure functions: no store
access, no I/O.

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import json
import os
import re

CLAUDE = "claude"
CODEX = "codex"
CURSOR = "cursor"

# Cursor names events in camelCase; Claude Code and Codex in PascalCase. Keyed on
# the payload, not on CURSOR_* env vars, because Claude Code run inside Cursor's
# terminal can inherit those.
_CURSOR_EVENTS = {
    "sessionStart": "SessionStart",
    "sessionEnd": "SessionEnd",
    "afterFileEdit": "PostToolUse",
    "afterShellExecution": "PostToolUse",
}

_PATCH_HEADER = re.compile(
    r"^\*\*\* (?:Add|Update|Delete) File: (.+?)\s*$|^\*\*\* Move to: (.+?)\s*$", re.MULTILINE
)


def detect_agent(payload):
    event = payload.get("hook_event_name")
    if isinstance(event, str) and event[:1].islower():
        return CURSOR
    if payload.get("tool_name") == "apply_patch":
        return CODEX
    return CLAUDE


def normalize(payload, env):
    """Return Claude-shaped payloads for this hook call; [] means nothing to do."""
    agent = detect_agent(payload)
    if agent == CURSOR:
        return _from_cursor(payload, env)
    if agent == CODEX:
        return _from_codex_patch(payload)
    return [payload]


def format_context(agent, event_name, text):
    if agent == CURSOR:
        return json.dumps({"additional_context": text})
    return json.dumps(
        {"hookSpecificOutput": {"hookEventName": event_name, "additionalContext": text}}
    )


def patch_paths(patch, cwd):
    """Absolute paths named by a Codex apply_patch, first-seen order."""
    paths = []
    for match in _PATCH_HEADER.finditer(patch):
        path = match.group(1) or match.group(2)
        if not os.path.isabs(path):
            if not (isinstance(cwd, str) and cwd):
                continue
            path = os.path.join(cwd, path)
        path = os.path.normpath(path)
        if path not in paths:
            paths.append(path)
    return paths


def _cursor_root(payload, env):
    root = env.get("CURSOR_PROJECT_DIR")
    if root:
        return root
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots and isinstance(roots[0], str) and roots[0]:
        return roots[0]
    return None


def _from_cursor(payload, env):
    event = payload.get("hook_event_name")
    if event not in _CURSOR_EVENTS:
        return []
    out = {"cwd": _cursor_root(payload, env), "hook_event_name": _CURSOR_EVENTS[event]}
    if event == "afterFileEdit":
        out["tool_name"] = "MultiEdit"
        out["tool_input"] = {
            "file_path": payload.get("file_path"),
            "edits": payload.get("edits") or [],
        }
    elif event == "afterShellExecution":
        out["tool_name"] = "Bash"
        out["tool_input"] = {"command": payload.get("command") or ""}
    return [out]


def _patch_text(payload):
    command = (payload.get("tool_input") or {}).get("command")
    if isinstance(command, list):
        return "\n".join(part for part in command if isinstance(part, str))
    return command if isinstance(command, str) else ""


def _changes_content(patch):
    """False only when every +/- line pair differs by whitespace alone."""
    removed, added = [], []
    for line in patch.splitlines():
        if line.startswith("***") or line.startswith("@@"):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    if not removed and not added:
        return True
    return "".join("".join(removed).split()) != "".join("".join(added).split())


def _from_codex_patch(payload):
    patch = _patch_text(payload)
    if patch and not _changes_content(patch):
        return []
    paths = patch_paths(patch, payload.get("cwd"))
    if not paths:
        # Unparseable patch: capture against the session root, like the Bash trigger.
        return [dict(payload, tool_name="Edit", tool_input={})]
    return [dict(payload, tool_name="Edit", tool_input={"file_path": path}) for path in paths]
