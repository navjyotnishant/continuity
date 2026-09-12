"""hooks/session-start.py — SessionStart hook (T016).

A thin dispatcher over lib/select_context.py, per
contracts/hook-io-contract.md -> SessionStart: read the stdin payload,
resolve `.continuity/` from `cwd`, gate on schema compatibility, and emit the
labeled context block as `hookSpecificOutput.additionalContext`.

Always prints valid JSON and always exits 0. A project with no
`.continuity/`, an unsupported schema, or any internal failure emits the
envelope with no `additionalContext` key at all — an absent key is how a
session proceeds normally with nothing injected (FR-007/FR-012).

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.common import continuity_dir, continuity_log
from lib.migrate import metadata_check_and_migrate
from lib.select_context import select_context

HOOK_EVENT_NAME = "SessionStart"


def build_context(cwd):
    """Return the context block for a project root, or "" for nothing to inject."""
    continuity_dir_path = continuity_dir(cwd)
    if not os.path.isdir(continuity_dir_path):
        return ""
    if not metadata_check_and_migrate(continuity_dir_path):
        return ""
    return select_context(continuity_dir_path)


def main():
    payload = {}
    try:
        raw = sys.stdin.read()
        if raw.strip():
            payload = json.loads(raw)
    except (OSError, ValueError):
        payload = {}

    cwd = payload.get("cwd") or os.getcwd()

    try:
        context = build_context(cwd)
    except Exception as error:  # fail open: never block the session starting
        continuity_log(
            continuity_dir(cwd), "session-start-load", "unreadable", type(error).__name__
        )
        context = ""

    output = {"hookSpecificOutput": {"hookEventName": HOOK_EVENT_NAME}}
    if context:
        output["hookSpecificOutput"]["additionalContext"] = context

    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
