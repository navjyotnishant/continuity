"""lib/lock.py — advisory store lock, one `os.mkdir()` call deep.

research.md R2: `os.mkdir()` either succeeds or raises FileExistsError
atomically on every filesystem, on all three target platforms, with no
helper binary (`flock`) and no platform-specific API (a Windows named
mutex). A lock older than STALE_SECONDS is treated as abandoned by a crashed
writer and broken, which is the one failure `os.mkdir()` locking cannot
otherwise self-heal from.

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import os
import time

STALE_SECONDS = 10
DEFAULT_TIMEOUT = 5.0
RETRY_INTERVAL = 0.05


def lock_path(continuity_dir_path):
    """Return the lock directory path for a `.continuity/` store."""
    return os.path.join(continuity_dir_path, ".lock")


def lock_acquire(continuity_dir_path, timeout=DEFAULT_TIMEOUT):
    """Claim the store lock. Returns True on success, False on failure.

    Never raises: an unwritable `.continuity/` is a False, not an
    exception, because every caller is a fail-open background path (FR-012).
    """
    path = lock_path(continuity_dir_path)
    deadline = time.monotonic() + timeout

    while True:
        try:
            os.mkdir(path)
            return True
        except FileExistsError:
            if _is_stale(path):
                _break_stale(path)
        except OSError:
            # Missing or unwritable parent — nothing to retry for.
            return False

        if time.monotonic() >= deadline:
            return False
        time.sleep(RETRY_INTERVAL)


def lock_release(continuity_dir_path):
    """Release the store lock. Silent if it is already gone (stale-broken)."""
    try:
        os.rmdir(lock_path(continuity_dir_path))
    except OSError:
        pass


def _is_stale(path):
    try:
        return (time.time() - os.path.getmtime(path)) > STALE_SECONDS
    except OSError:
        # Vanished between the mkdir failure and here — not stale, just gone.
        return False


def _break_stale(path):
    try:
        os.rmdir(path)
    except OSError:
        pass
