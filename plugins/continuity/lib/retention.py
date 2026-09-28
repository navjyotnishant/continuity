"""lib/retention.py — prune what is past its window, touch nothing else (T030).

Three jobs, each bounded by data-model.md and
contracts/file-format-contract.md:

- `sessions/*.md` older than `retention_days` (default 60, read fresh from
  `metadata.json` every run) are deleted. Age comes from the *filename's*
  timestamp, not mtime, because a clone or a checkout rewrites mtime and
  would silently change what "old" means.
- `errors.log` lines older than the same window are trimmed.
- `<name>.tmp.*` files older than an hour are swept as crash debris — the
  orphan an interrupted `atomic_write` leaves behind.

The durable files (`state.md`, `decisions.md`, `tasks.md`, `learnings.md`)
are never pruned at any age: a fact promoted into them is durable precisely
because handoff pruning cannot reach it (Q6).

Nothing here raises. It runs at the tail of a detached writer, where an
exception would be invisible anyway (FR-012).

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import os
from datetime import datetime, timedelta, timezone

from lib.atomic_write import atomic_write
from lib.common import continuity_log, read_metadata_defaults

SESSIONS_DIRNAME = "sessions"
TMP_MARKER = ".tmp."
TMP_ORPHAN_MAX_AGE = timedelta(hours=1)
FILENAME_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"
LOG_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def retention_prune(continuity_dir_path):
    """Prune aged-out handoffs, log lines, and crash debris. Never raises."""
    retention_days, _ = read_metadata_defaults(continuity_dir_path)
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)

    _prune_sessions(continuity_dir_path, cutoff)
    _trim_errors_log(continuity_dir_path, cutoff)
    _sweep_tmp_orphans(continuity_dir_path)


def _prune_sessions(continuity_dir_path, cutoff):
    sessions_path = os.path.join(continuity_dir_path, SESSIONS_DIRNAME)
    try:
        names = os.listdir(sessions_path)
    except OSError:
        return

    for name in names:
        stamped = _timestamp_from_filename(name)
        # A name whose timestamp will not parse is left alone: deleting a
        # file this module cannot date would be guessing at its age.
        if stamped is None or stamped >= cutoff:
            continue
        try:
            os.unlink(os.path.join(sessions_path, name))
        except OSError:
            continuity_log(
                continuity_dir_path, "retention", "write-failed", "sessions/" + name
            )


def _trim_errors_log(continuity_dir_path, cutoff):
    target = os.path.join(continuity_dir_path, "errors.log")
    try:
        with open(target, "r", encoding="utf-8", errors="replace") as handle:
            lines = handle.readlines()
    except OSError:
        return

    kept = [line for line in lines if _log_line_survives(line, cutoff)]
    if len(kept) == len(lines):
        return

    try:
        if kept:
            atomic_write(target, "".join(kept))
        else:
            # Every line aged out. atomic_write refuses empty content (it
            # exists to stop a write from blanking a file), so the
            # equivalent outcome here is removing the log entirely.
            os.unlink(target)
    except OSError:
        continuity_log(continuity_dir_path, "retention", "write-failed", "errors.log")


def _log_line_survives(line, cutoff):
    """Keep a line unless it is datable *and* older than the cutoff.

    A line that does not match the four-field shape is skipped rather than
    treated as a parse failure (contracts/file-format-contract.md) — and
    skipping means leaving it in place, not deleting an entry whose age is
    unknown.
    """
    fields = line.split("|")
    if len(fields) < 4:
        return True
    try:
        stamped = datetime.strptime(fields[0].strip(), LOG_TIMESTAMP_FORMAT)
    except ValueError:
        return True
    return stamped.replace(tzinfo=timezone.utc) >= cutoff


def _sweep_tmp_orphans(continuity_dir_path):
    cutoff = datetime.now(timezone.utc) - TMP_ORPHAN_MAX_AGE
    for root, _dirs, names in os.walk(continuity_dir_path):
        for name in names:
            if TMP_MARKER not in name:
                continue
            path = os.path.join(root, name)
            try:
                # mtime is the only age a temp file has — its name carries no
                # timestamp, unlike a handoff's.
                modified = datetime.fromtimestamp(os.path.getmtime(path), timezone.utc)
                if modified < cutoff:
                    os.unlink(path)
            except OSError:
                continuity_log(
                    continuity_dir_path, "retention", "write-failed", "tmp orphan: " + name
                )


def _timestamp_from_filename(name):
    """Parse `<UTC-timestamp>-<pid>.md` into an aware datetime, or None."""
    try:
        stamped = datetime.strptime(name.split("-", 1)[0], FILENAME_TIMESTAMP_FORMAT)
    except ValueError:
        return None
    return stamped.replace(tzinfo=timezone.utc)
