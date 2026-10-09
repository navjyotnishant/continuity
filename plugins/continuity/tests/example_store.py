"""tests/example_store.py — builds the example store committed in docs/examples/.

The inputs are the plain-text notes in docs/examples/staged-notes/run-N/ (what an
agent writes to `.continuity/.staged/`). Each run is fed to the real writer with a
frozen clock, so docs/examples/store/ is exactly what Continuity produces and
tests/test_examples_in_sync.py fails if the two ever drift.

Regenerate after changing the writer or the notes:

    python3 plugins/continuity/tests/example_store.py --write
"""

import os
import sys
import tempfile
from unittest import mock

PLUGIN_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, PLUGIN_ROOT)

import lib.write_memory as wm  # noqa: E402

EXAMPLES = os.path.normpath(os.path.join(PLUGIN_ROOT, "..", "..", "docs", "examples"))
NOTES = os.path.join(EXAMPLES, "staged-notes")
STORE = os.path.join(EXAMPLES, "store")

RUNS = [("run-1", "2026-09-14T09:00:00Z"), ("run-2", "2026-09-15T10:30:00Z")]
FILES = ["state.md", "tasks.md", "decisions.md", "learnings.md", ".gitignore"]


def _stage(project, run, stamp):
    staged = os.path.join(project, ".continuity", ".staged")
    os.makedirs(staged, exist_ok=True)
    for name in sorted(os.listdir(os.path.join(NOTES, run))):
        kind, suffix = name.split("-", 1)
        with open(os.path.join(NOTES, run, name), encoding="utf-8") as source:
            text = source.read()
        with open(os.path.join(staged, "{}-{}-{}".format(kind, stamp, suffix)), "w", encoding="utf-8") as out:
            out.write(text)


def build():
    """Return {relative path: text} for the example store."""
    files = {}
    with tempfile.TemporaryDirectory() as project:
        for run, iso in RUNS:
            stamp = iso.replace("-", "").replace(":", "")
            _stage(project, run, stamp)
            # Frozen clock and pid; no retention sweep, so the output never
            # depends on today's date.
            with mock.patch.object(wm, "_now", lambda iso=iso: iso), mock.patch.object(
                wm, "_filename_timestamp", lambda stamp=stamp: stamp
            ), mock.patch.object(wm.os, "getpid", lambda run=run: int(run[-1]) * 1000), mock.patch.object(
                wm, "retention_prune", lambda *_: None
            ):
                wm.write_memory(project, "session-end")
        store = os.path.join(project, ".continuity")
        for name in FILES:
            with open(os.path.join(store, name), encoding="utf-8") as handle:
                files[name] = handle.read()
        sessions = os.path.join(store, "sessions")
        for name in sorted(os.listdir(sessions)):
            with open(os.path.join(sessions, name), encoding="utf-8") as handle:
                files["sessions/" + name] = handle.read()
    return files


if __name__ == "__main__":
    built = build()
    if "--write" not in sys.argv:
        for path, text in built.items():
            print("=== " + path + "\n" + text)
        sys.exit(0)
    for path, text in built.items():
        target = os.path.join(STORE, path)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    print("wrote %d files to %s" % (len(built), STORE))
