"""hooks/session-start.py — SessionStart hook (T016).

A thin dispatcher over lib/select_context.py, per
contracts/hook-io-contract.md -> SessionStart: read the stdin payload,
resolve `.continuity/` from `cwd`, gate on schema compatibility, and emit the
labeled context block as `hookSpecificOutput.additionalContext`.

A project with no `.continuity/` yet has its store seeded here, so a freshly
installed plugin has one from its very first session rather than from
whenever a checkpoint first fires (CONTINUI-46). Seeding is best-effort: it
never raises and never changes what this hook emits.

Always prints valid JSON and always exits 0. `additionalContext` always
carries at least `select_context.STAGING_INSTRUCTIONS` (CONTINUI-47) — the
Content Channel convention Claude needs to know to ever record anything —
plus a history section on top of it whenever the store has one. A project
with no `.continuity/`, an unsupported schema, or any internal failure omits
only the *history* half; the key itself is never absent (FR-007/FR-012 still
hold for history — there is simply nothing else fixed left to omit).

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.common import continuity_dir, continuity_log
from lib.migrate import metadata_check_and_migrate, metadata_ensure, seed_store
from lib.select_context import STAGING_INSTRUCTIONS, select_context

HOOK_EVENT_NAME = "SessionStart"


def read_payload():
    """Return the stdin payload as a dict — `{}` for anything unusable.

    Valid JSON that is not an object (a bare list or string) is as much a
    malformed payload as unparseable bytes are, and both have to land on the
    same fail-open path: stdin is this script's trust boundary, and a hook
    that raises here has already violated "always exits 0".
    """
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        parsed = json.loads(raw)
    except (OSError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def build_context(cwd):
    """Return the context block for a project root.

    Always at least STAGING_INSTRUCTIONS (CONTINUI-47); a history section on
    top of it whenever the store has one to report.

    A project with no `.continuity/` at all is a fresh install: seed the store
    here (CONTINUI-46) instead of waiting for whichever checkpoint happens to
    fire first. The seed is a handful of small template writes, cheap enough
    to stay on this path — a store created this instant has no prior session
    to report, so it gets the instructions with no history alongside them.
    """
    continuity_dir_path = continuity_dir(cwd)
    if not os.path.isdir(continuity_dir_path):
        metadata_ensure(continuity_dir_path)
        seed_store(continuity_dir_path)
        return STAGING_INSTRUCTIONS + "\n"
    if not metadata_check_and_migrate(continuity_dir_path):
        return STAGING_INSTRUCTIONS + "\n"
    return select_context(continuity_dir_path)


def main():
    payload = read_payload()
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()

    try:
        context = build_context(cwd)
    except Exception as error:  # fail open: never block the session starting
        continuity_log(
            continuity_dir(cwd), "session-start-load", "unreadable", type(error).__name__
        )
        context = STAGING_INSTRUCTIONS + "\n"

    output = {"hookSpecificOutput": {"hookEventName": HOOK_EVENT_NAME}}
    output["hookSpecificOutput"]["additionalContext"] = context

    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
