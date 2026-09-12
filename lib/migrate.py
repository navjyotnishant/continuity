"""lib/migrate.py — `metadata.json` creation and schema compatibility.

Implements contracts/file-format-contract.md -> `metadata.json`: a reader
supports its own `schema_version` and the one immediately prior, migrates an
older-but-supported store forward before use, and on an unsupported *newer*
version performs no write of any kind, logs `unsupported-schema`, and treats
the store as absent for that operation (Q9, fail open).

Every read/write path calls `metadata_check_and_migrate()` before touching
anything else in the store, so the "operating on two formats side by side"
case cannot arise.

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import json
import os
from datetime import datetime, timezone

from lib.atomic_write import atomic_write
from lib.common import continuity_log

SCHEMA_VERSION = "1.0"

_TEMPLATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates",
    "metadata.json.tmpl",
)


def metadata_ensure(continuity_dir_path):
    """Create `metadata.json` from the seed template if it is absent.

    Returns True if the file exists afterwards. Never raises — a store whose
    metadata cannot be written still works, it just re-tries next run.
    """
    target = os.path.join(continuity_dir_path, "metadata.json")
    if os.path.isfile(target):
        return True

    try:
        with open(_TEMPLATE_PATH, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        metadata["created_at"] = _now()
        atomic_write(target, json.dumps(metadata, indent=2) + "\n")
        return True
    except (OSError, ValueError) as error:
        continuity_log(
            continuity_dir_path, "migrate", "write-failed", type(error).__name__
        )
        return False


def metadata_check_and_migrate(continuity_dir_path):
    """Return True when this store is safe to read/write, False to skip it.

    False means "fail open, touch nothing" — the store is at a schema version
    this plugin does not understand.
    """
    target = os.path.join(continuity_dir_path, "metadata.json")

    try:
        with open(target, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
        on_disk = metadata.get("schema_version")
        if not isinstance(on_disk, str):
            raise ValueError("schema_version missing")
    except FileNotFoundError:
        # Absent metadata.json alongside other files is defined as "1.0",
        # the version that predates metadata.json's own introduction.
        return True
    except (OSError, ValueError) as error:
        continuity_log(
            continuity_dir_path, "migrate", "corrupted", "metadata.json: " + type(error).__name__
        )
        return True

    if on_disk == SCHEMA_VERSION:
        return True

    if _major(on_disk) > _major(SCHEMA_VERSION):
        continuity_log(
            continuity_dir_path, "migrate", "unsupported-schema", "schema_version ahead of plugin"
        )
        return False

    if _major(on_disk) < _major(SCHEMA_VERSION) - 1:
        # More than one major version behind — outside the supported window.
        continuity_log(
            continuity_dir_path, "migrate", "unsupported-schema", "schema_version too old"
        )
        return False

    # Older-but-supported, or the same major at a lower minor: bring the
    # marker forward. No durable file's format has changed within 1.x, so
    # there is nothing else to rewrite yet; a future format change adds its
    # rewrite here.
    metadata["schema_version"] = SCHEMA_VERSION
    try:
        atomic_write(target, json.dumps(metadata, indent=2) + "\n")
    except OSError as error:
        continuity_log(
            continuity_dir_path, "migrate", "write-failed", type(error).__name__
        )
    return True


def _major(version):
    try:
        return int(str(version).split(".")[0])
    except (TypeError, ValueError):
        return 0


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
