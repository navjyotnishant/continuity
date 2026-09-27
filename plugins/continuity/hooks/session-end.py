"""hooks/session-end.py — SessionEnd hook (T022).

Per contracts/hook-io-contract.md -> SessionEnd: read the stdin payload,
launch lib/write_memory.py detached, exit with no output. There is no
classification step here, unlike PostToolUse — SessionEnd fires the writer
unconditionally and lets write_memory.py apply FR-011's no-op rule itself
(an empty `.staged/` produces no file change), which keeps this script a
plain dispatcher.

The detach idiom is duplicated from capture-trigger.py rather than shared:
`hooks/*.py` are invoked by path and never imported (their names are
hyphenated), and a hook that reached into `lib/` for this would import a
module on the one path that must stay a bare-stdlib startup.

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import json
import os
import subprocess
import sys

PLUGIN_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRITER = os.path.join(PLUGIN_ROOT, "lib", "write_memory.py")
TRIGGER_KIND = "session-end"


def detach_kwargs():
    """Platform-specific arguments that orphan the writer (research.md R4)."""
    if os.name == "nt":
        return {
            "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS
        }
    return {"start_new_session": True}


def launch_writer(cwd, writer=WRITER):
    """Fire the writer and return immediately. Never raises."""
    try:
        subprocess.Popen(
            [sys.executable or "python3", writer, cwd, TRIGGER_KIND],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,
            **detach_kwargs()
        )
    except (OSError, ValueError):
        _log(cwd, "write-failed", "writer not launched")


def _log(cwd, failure_kind, detail):
    # Imported lazily so the ordinary path stays a bare-stdlib startup.
    sys.path.insert(0, PLUGIN_ROOT)
    from lib.common import continuity_dir, continuity_log

    continuity_log(continuity_dir(cwd), "session-end", failure_kind, detail)


def main():
    try:
        raw = sys.stdin.read()
        parsed = json.loads(raw) if raw.strip() else {}
    except (OSError, ValueError):
        return 0

    # Valid JSON that is not an object is as malformed as unparseable bytes,
    # and neither may raise out of a hook (always-exit-0).
    if not isinstance(parsed, dict):
        return 0

    cwd = parsed.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return 0

    launch_writer(cwd)
    return 0


if __name__ == "__main__":
    sys.exit(main())
