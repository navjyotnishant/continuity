"""hooks/stop.py — Stop hook (CONTINUI-66).

Author: Navjyot Nishant
Created: 2026-10-08
Last updated: 2026-10-08
Description: End-of-turn nudge to stage a continuity note after a turn that edited files.

Capture used to depend on the agent remembering one SessionStart instruction,
and it often did not: a store could sit empty for days while every trigger
fired. This hook closes that gap at the one moment the agent can still act on
it — the end of its own turn.

The decision is two file checks, no git, no model call:

- `.continuity/.turn-edited` exists — capture-trigger.py set it on a
  meaningful change this turn and nothing has cleared it since;
- `.continuity/.staged/` holds no note — the writer has already consumed
  anything staged, but staging a note clears the marker, so a turn that
  staged something never reaches this check.

Both true means one nudge: Claude Code and Codex continue the same turn on a
`block` decision; Cursor sends a `followup_message`. The marker is removed
either way, so the next turn starts clean. On the re-entry pass
(`stop_hook_active` / `loop_count > 0`) it stays silent — one nudge per turn,
never a loop.

Always exits 0; any failure means no output, which lets the turn end (FR-012).

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import json
import os
import subprocess
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN_ROOT)

WRITER = os.path.join(PLUGIN_ROOT, "lib", "write_memory.py")
TURN_MARKER = ".turn-edited"

NUDGE = """[Continuity] Files changed this turn and no continuity note was staged. \
Most turns need no note: skip it when the change speaks for itself in the code \
or git history. Stage one only if a future session would otherwise lose \
something: a decision and its reason, a non-obvious learning, a task left \
unfinished or blocked, or where a multi-step piece of work stands. Then write \
1-5 lines to `{staged_dir}/<kind>-<UTC timestamp like 20260927T140501Z>-<n>.md`, \
kind one of decision, task, learning, handoff; a first-line `# heading` becomes \
its title. Either way, produce no further reply text."""


def read_payload():
    try:
        raw = sys.stdin.read()
        parsed = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def has_staged_note(staged_dir):
    try:
        return any(name.endswith(".md") for name in os.listdir(staged_dir))
    except OSError:
        return False


def detach_kwargs():
    """Platform-specific arguments that orphan the writer (research.md R4)."""
    if os.name == "nt":
        return {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
        }
    return {"start_new_session": True}


def launch_writer(cwd, writer=WRITER):
    """Consolidate staged notes in the background. Never raises.

    Launched from here because a note written through a shell redirect (Codex)
    is not a meaningful edit to capture-trigger.py, so nothing else would
    consolidate it until a later git command.
    """
    try:
        subprocess.Popen(
            [sys.executable or "python3", writer, cwd, "stop"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            **detach_kwargs()
        )
    except (OSError, ValueError):
        pass


def decide(payload):
    """Return the nudge text for this Stop, or None to let the turn end."""
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    store = os.path.join(cwd, ".continuity")
    if has_staged_note(os.path.join(store, ".staged")):
        launch_writer(cwd)
    marker = os.path.join(store, TURN_MARKER)
    if not os.path.exists(marker):
        return None
    os.remove(marker)
    if payload.get("stop_hook_active") or payload.get("loop_count"):
        return None
    if payload.get("status") not in (None, "completed"):
        return None  # Cursor: an aborted or failed turn is not one to summarize
    staged_dir = os.path.join(os.path.abspath(store), ".staged")
    if has_staged_note(staged_dir):
        return None
    return NUDGE.format(staged_dir=staged_dir)


def main():
    try:
        from lib import agents

        raw = read_payload()
        agent = agents.detect_agent(raw)
        payloads = agents.normalize(raw, os.environ)
        text = decide(payloads[0]) if payloads else None
        if text:
            print(agents.format_stop_nudge(agent, text))
    except Exception as error:  # noqa: BLE001 — fail open: no output lets the turn end
        try:
            from lib.common import continuity_dir, continuity_log

            continuity_log(continuity_dir(os.getcwd()), "stop", "unreadable", type(error).__name__)
        except Exception:  # noqa: BLE001
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
