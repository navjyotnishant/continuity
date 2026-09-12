"""lib/migrate.py — `metadata.json` creation and schema-version compatibility.

Every read or write of a `.continuity/` store goes through
`metadata_check_and_migrate` first, so the rest of the plugin only ever
operates on a store whose format it understands. The three outcomes come
straight from `contracts/file-format-contract.md` -> `metadata.json`:

- the store's schema is this plugin's own    -> proceed, write nothing here
- the store's schema is the supported prior  -> migrate it forward, proceed
- anything else (newer, far older, garbage)  -> write NOTHING, log, fail open

"Fail open" means the caller treats the store as absent for this operation
(FR-012) rather than erroring or, worse, rewriting a file in a format it
does not understand. A False return is therefore not an exception — it is
the contract's defined behaviour, and callers gate on it.

"Supported prior" is read off the major version: a plugin understands its
own major and the one immediately before it, which is the same boundary the
contract draws for the unsupported-newer case ("major version ahead of what
this plugin understands"). At `schema_version` 1.0 the prior series is 0.x.

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import json
import os
import re
from datetime import datetime, timezone

from lib.atomic_write import atomic_write
from lib.common import continuity_log

CURRENT_SCHEMA_VERSION = "1.0"

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METADATA_TEMPLATE_PATH = os.path.join(_REPO_ROOT, "templates", "metadata.json.tmpl")

_OPERATION = "migrate"


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_MAJOR_PATTERN = re.compile(r"^(-?)([0-9]+)(?:\.|$)")

# Any major this long is numeric but absurd — clamped so the comparison stays
# a comparison instead of an arbitrary-precision conversion.
_MAJOR_DIGIT_LIMIT = 9
_MAJOR_CLAMP = 10 ** _MAJOR_DIGIT_LIMIT


def _major(version):
    """Return the integer major of a `<major>.<minor>` version, else None.

    Digits are counted before converting rather than handing the string
    straight to `int()`: CPython 3.11+ refuses to convert a string of more
    than 4300 digits, so `int()` alone would classify the same absurd-but-
    numeric version as corrupted on one interpreter and as an unsupported
    newer schema on another. A store must get the same verdict on every
    Python this plugin supports, so an over-long run of digits is clamped —
    it is still unambiguously a number, and still unambiguously not a major
    version this plugin can read.
    """
    match = _MAJOR_PATTERN.match(str(version))
    if match is None:
        return None
    sign = -1 if match.group(1) else 1
    digits = match.group(2)
    if len(digits) > _MAJOR_DIGIT_LIMIT:
        return sign * _MAJOR_CLAMP
    return sign * int(digits)


def _serialize(metadata):
    return json.dumps(metadata, indent=2) + "\n"


def metadata_ensure(continuity_dir_path):
    """Create `metadata.json` from the shipped template when it is absent.

    Returns True when the file exists afterwards, False when it could not be
    created (fail open — the caller skips, nothing raises). An existing
    `metadata.json` is never touched, including one at a schema version this
    plugin does not support: deciding what to do about that is
    `metadata_check_and_migrate`'s job, not this one's.

    `created_at` is stamped at creation time and `schema_version` is taken
    from this module rather than the template, so a stale template cannot
    mislabel a store it seeds.
    """
    metadata_path = os.path.join(continuity_dir_path, "metadata.json")
    if os.path.exists(metadata_path):
        return True

    # The three template failures are three different operator problems — a
    # broken install, a permission mistake, and a bad edit — so they log as
    # three different failure kinds rather than one catch-all.
    try:
        with open(METADATA_TEMPLATE_PATH, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
    except FileNotFoundError:
        continuity_log(
            continuity_dir_path, _OPERATION, "missing", "templates/metadata.json.tmpl"
        )
        return False
    except OSError:
        continuity_log(
            continuity_dir_path, _OPERATION, "unreadable", "templates/metadata.json.tmpl"
        )
        return False
    except ValueError:
        continuity_log(
            continuity_dir_path, _OPERATION, "corrupted", "templates/metadata.json.tmpl"
        )
        return False

    if not isinstance(metadata, dict):
        continuity_log(
            continuity_dir_path, _OPERATION, "corrupted", "templates/metadata.json.tmpl"
        )
        return False

    metadata["schema_version"] = CURRENT_SCHEMA_VERSION
    metadata["created_at"] = _utc_now()

    try:
        os.makedirs(continuity_dir_path, exist_ok=True)
        atomic_write(metadata_path, _serialize(metadata))
    except (OSError, ValueError):
        continuity_log(continuity_dir_path, _OPERATION, "write-failed", "metadata.json")
        return False
    return True


def metadata_check_and_migrate(continuity_dir_path):
    """Return True when this store is safe to use, False to fail open.

    Migrates a store at the supported prior schema version forward before
    returning True. Writes nothing at all on any other non-current version,
    per the contract's "no write of any kind" rule.
    """
    metadata_path = os.path.join(continuity_dir_path, "metadata.json")

    try:
        with open(metadata_path, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
    except FileNotFoundError:
        # An absent metadata.json is defined as the current version, so there
        # is nothing to migrate and nothing to refuse.
        return True
    except (OSError, ValueError):
        continuity_log(continuity_dir_path, _OPERATION, "corrupted", "metadata.json")
        return False

    if not isinstance(metadata, dict):
        continuity_log(continuity_dir_path, _OPERATION, "corrupted", "metadata.json")
        return False

    store_major = _major(metadata.get("schema_version"))
    current_major = _major(CURRENT_SCHEMA_VERSION)

    if store_major is None:
        continuity_log(
            continuity_dir_path, _OPERATION, "corrupted", "metadata.json schema_version"
        )
        return False

    # Same major, any minor: readable as-is. A newer minor written by a newer
    # plugin stays at its own version — the contract only makes a major
    # version ahead unsupported, and rewriting it would be a downgrade.
    if store_major == current_major:
        return True

    if store_major == current_major - 1:
        return _migrate_forward(continuity_dir_path, metadata)

    # Newer major (a teammate's newer plugin wrote it), or so old this plugin
    # has no migration for it. Either way the format is unknown: log, touch
    # nothing, and let the caller proceed as if the store were absent.
    continuity_log(
        continuity_dir_path,
        _OPERATION,
        "unsupported-schema",
        "schema_version {}".format(str(metadata.get("schema_version"))[:40]),
    )
    return False


def _migrate_forward(continuity_dir_path, metadata):
    """Rewrite the store at the current schema version.

    No durable-file format has changed between schema versions yet, so
    migrating forward is exactly the `metadata.json` version bump the
    contract asks for. When a file format does change, rewrite those files
    here — atomically, all of them — before the bump below, so a store is
    never left half-migrated with its version already claiming otherwise.
    """
    metadata["schema_version"] = CURRENT_SCHEMA_VERSION
    try:
        atomic_write(
            os.path.join(continuity_dir_path, "metadata.json"), _serialize(metadata)
        )
    except (OSError, ValueError):
        continuity_log(continuity_dir_path, _OPERATION, "write-failed", "metadata.json")
        return False
    return True
