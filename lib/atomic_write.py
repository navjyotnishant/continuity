"""lib/atomic_write.py — the single write primitive every other module uses.

Implements contracts/file-format-contract.md -> Atomicity: content goes to a
`<target basename>.tmp.*` file in the *same* directory as `<target>` (so
`os.replace()` stays within one filesystem, and so lib/retention.py can glob
the crash debris a killed process leaves behind), then `os.replace()` puts it
onto `<target>`. A reader therefore never observes a half-written file.

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import os
import tempfile


def atomic_write(target, content):
    """Atomically replace `target` with `content`. Returns True if written.

    Returns False without touching `target` when `content` is empty or
    whitespace-only — data-model.md's State Note rule: a trigger that
    produced no meaningful summary must not silently wipe prior state.

    Raises OSError on a genuine write/replace failure; every caller is a
    fail-open path that catches it (FR-012).
    """
    if not content.strip():
        return False

    directory = os.path.dirname(os.path.abspath(target))
    os.makedirs(directory, exist_ok=True)

    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        newline="\n",
        dir=directory,
        prefix=os.path.basename(target) + ".tmp.",
        delete=False,
    )
    try:
        with handle:
            handle.write(content)
        os.replace(handle.name, target)
    except OSError:
        try:
            os.unlink(handle.name)
        except OSError:
            pass
        raise

    return True
