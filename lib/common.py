"""lib/common.py — shared path resolution, failure logging, and metadata
defaults used by every other Continuity script.

Every function is scoped by an explicit directory argument (a project `cwd`
or a `.continuity` dir) rather than a global/env var, because every hook in
contracts/hook-io-contract.md receives its project `cwd` on stdin per
invocation — there is no ambient "current project" to assume.

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import json
import os
from datetime import datetime, timezone


def continuity_dir(cwd):
    """Return the `.continuity/` path for a given project `cwd`.

    Pure string/path resolution — does not check existence or create
    anything.
    """
    return os.path.join(os.path.normpath(cwd), ".continuity")


def continuity_log(continuity_dir_path, operation, failure_kind, detail):
    """Append one scrubbed, pipe-delimited line to `errors.log`.

    Format (contracts/file-format-contract.md):
        <ISO-8601 UTC timestamp> | <operation> | <failure-kind> | <detail>

    Fail-open (FR-012): creates `continuity_dir_path` if missing; if the
    append itself fails for any reason (no permission, disk full, missing
    parent), this silently no-ops rather than raising an error of its own.
    """
    try:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        def scrub(field):
            return str(field).replace("|", " ").replace("\n", " ")

        line = "{} | {} | {} | {}\n".format(
            timestamp, scrub(operation), scrub(failure_kind), scrub(detail)
        )

        os.makedirs(continuity_dir_path, exist_ok=True)
        errors_log_path = os.path.join(continuity_dir_path, "errors.log")
        with open(errors_log_path, "a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError:
        pass


def read_metadata_defaults(continuity_dir_path):
    """Read `retention_days`/`git_tracked` out of `metadata.json`.

    Defaults to 60 / True (data-model.md's stated defaults) when the file
    is absent, unreadable, or unparseable — never raises, never writes
    anything (reading defaults is not the same operation as
    `lib/migrate.py`'s `metadata_ensure`, which creates the file).
    """
    retention_days = 60
    git_tracked = True

    metadata_path = os.path.join(continuity_dir_path, "metadata.json")
    try:
        with open(metadata_path, "r", encoding="utf-8") as handle:
            metadata = json.load(handle)
    except (OSError, ValueError):
        return retention_days, git_tracked

    if isinstance(metadata.get("retention_days"), int):
        retention_days = metadata["retention_days"]
    if isinstance(metadata.get("git_tracked"), bool):
        git_tracked = metadata["git_tracked"]

    return retention_days, git_tracked
