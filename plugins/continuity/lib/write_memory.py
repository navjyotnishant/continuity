"""lib/write_memory.py — the detached background writer (T017).

Consolidates only. It never composes prose: the natural-language body of a
decision, task, learning, or handoff is written by Claude itself into
`.continuity/.staged/<kind>-<UTC-timestamp>-<pid>.md` before any trigger
fires — the Content Channel of contracts/hook-io-contract.md and plan.md
(T017a). This module reads those staged notes, secret-scans them, appends
them into the matching durable file, writes one session handoff, and removes
the notes it consumed.

Run as a subprocess by every trigger (`python3 lib/write_memory.py <cwd>
<trigger-kind>`), never imported by a hook, so that a hook never waits on it
(FR-010). An empty `.staged/` produces no file change at all, not even a
lock (FR-011), and every failure path logs and returns rather than raising,
because the caller is a detached process nobody is watching (FR-012).

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import argparse
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.atomic_write import atomic_write
from lib.common import continuity_dir, continuity_log
from lib.lock import lock_acquire, lock_release
from lib.migrate import (
    SEED_FILES,
    metadata_check_and_migrate,
    metadata_ensure,
    seed_store,
)
from lib.retention import retention_prune
from lib.secret_scan import secret_scan_line

STAGED_DIRNAME = ".staged"
SESSIONS_DIRNAME = "sessions"

# The Content Channel's `<kind>` tags, and where each one lands. `handoff`
# lands in sessions/ and `state` rewrites state.md in place; both are routed
# separately from these append-only files.
DURABLE_FILE = {
    "decision": "decisions.md",
    "task": "tasks.md",
    "learning": "learnings.md",
}
ENTRY_HEADING = {"decision": "Decision", "task": "Task", "learning": "Learning"}
TITLE_MAX = 72
DEFAULT_TASK_STATUS = "active"
TASK_STATUSES = ("active", "blocked", "done")
STATE_FILE = "state.md"
STATE_HEADING = "# Project state"
_TITLE_LINE = re.compile(r"^\s*title\s*:\s*(\S.*?)\s*$", re.IGNORECASE)
_STATUS_LINE = re.compile(r"^\s*status\s*:\s*(\w+)\s*$", re.IGNORECASE)


def staged_dir(continuity_dir_path):
    """Return the Content Channel directory for a store."""
    return os.path.join(continuity_dir_path, STAGED_DIRNAME)


def staged_name(kind):
    """Return the filename a staged note of `kind` must use (T017a)."""
    return "{}-{}-{}.md".format(kind, _filename_timestamp(), os.getpid())


def write_memory(cwd, trigger_kind):
    """Consolidate staged notes into the store. Returns the handoff path or None.

    None means "nothing was written" — either nothing was staged (the
    ordinary no-op) or a fail-open path declined to write.
    """
    continuity_dir_path = continuity_dir(cwd)
    staged = _staged_files(continuity_dir_path)
    if not staged:
        return None

    if not metadata_check_and_migrate(continuity_dir_path):
        # Unsupported newer schema: no write of any kind, already logged.
        return None
    metadata_ensure(continuity_dir_path)

    if not lock_acquire(continuity_dir_path):
        continuity_log(
            continuity_dir_path, "write-memory", "lock-unavailable", "store busy"
        )
        return None

    try:
        # Seeding is itself a store write, so it belongs inside the lock: a
        # run that never got the lock must leave the store exactly as it
        # found it, not leave behind the templates of files it then declined
        # to append to.
        seed_store(continuity_dir_path)
        handoff_path = _consolidate(continuity_dir_path, staged, trigger_kind)
        _prune(continuity_dir_path)
        return handoff_path
    finally:
        lock_release(continuity_dir_path)


def _prune(continuity_dir_path):
    """Sweep what is past its retention window, under the lock we already hold.

    Retention piggybacks on this run rather than scheduling a process of its
    own (plan.md's Implementation Order step 4), and only on the path that
    actually wrote: a store that was skipped is a store nothing may delete
    from. A prune failure must not cost the caller the handoff it just got,
    so the write is reported even when the sweep is not.
    """
    try:
        retention_prune(continuity_dir_path)
    except Exception as error:  # noqa: BLE001 — fail open (FR-012)
        continuity_log(
            continuity_dir_path, "retention", "write-failed", type(error).__name__
        )


def _consolidate(continuity_dir_path, staged, trigger_kind):
    timestamp = _now()
    entries = {kind: [] for kind in DURABLE_FILE}
    task_notes = []
    state_notes = []
    handoff_body = []
    consumed = []

    for path in staged:
        kind = _kind_of(path)
        text = _read(path)
        if kind is None or text is None:
            continuity_log(
                continuity_dir_path,
                "write-memory",
                "unreadable" if kind else "corrupted",
                "staged note dropped: " + os.path.basename(path),
            )
            consumed.append(path)
            continue

        scrubbed = _scrub(continuity_dir_path, text)
        if not scrubbed.strip():
            continuity_log(
                continuity_dir_path,
                "write-memory",
                "secret-blocked",
                "staged note dropped whole: " + os.path.basename(path),
            )
            consumed.append(path)
            continue

        if kind == "handoff":
            handoff_body.append(scrubbed.strip())
        elif kind == "task":
            task_notes.append(scrubbed)
        elif kind == "state":
            state_notes.append(scrubbed)
        else:
            entries[kind].append(_entry_text(kind, scrubbed, timestamp))
        consumed.append(path)

    counts = {kind: len(value) for kind, value in entries.items()}
    counts["task"] = len(task_notes)
    for kind, texts in entries.items():
        if texts:
            _append_entries(continuity_dir_path, DURABLE_FILE[kind], texts)
    if task_notes:
        _upsert_tasks(continuity_dir_path, task_notes, timestamp)
    if state_notes:
        counts["state"] = 1 if _write_state(continuity_dir_path, state_notes, timestamp) else 0

    handoff_path = _write_handoff(
        continuity_dir_path, trigger_kind, timestamp, "\n\n".join(handoff_body), counts
    )

    for path in consumed:
        try:
            os.unlink(path)
        except OSError:
            continuity_log(
                continuity_dir_path,
                "write-memory",
                "write-failed",
                "staged note not removed: " + os.path.basename(path),
            )

    return handoff_path


# --- staged notes (the Content Channel) -----------------------------------


def _staged_files(continuity_dir_path):
    try:
        names = sorted(
            name
            for name in os.listdir(staged_dir(continuity_dir_path))
            if name.endswith(".md")
        )
    except OSError:
        return []
    return [os.path.join(staged_dir(continuity_dir_path), name) for name in names]


def _kind_of(path):
    """Route on the staged filename's `<kind>` prefix alone (T017a)."""
    kind = os.path.basename(path).split("-", 1)[0]
    if kind in DURABLE_FILE or kind in ("handoff", "state"):
        return kind
    return None


def _read(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _scrub(continuity_dir_path, text):
    """Drop every line the secret gate matches, keep the rest (R5).

    Only the matched pattern's *name* is logged — never the matched text
    (data-model.md's Failure Log Entry rule).
    """
    kept = []
    for line in text.splitlines():
        matched = secret_scan_line(line)
        if matched:
            continuity_log(
                continuity_dir_path, "secret-scan-block", "secret-blocked", matched
            )
            continue
        kept.append(line)
    return "\n".join(kept)


# --- durable entries ------------------------------------------------------


def _entry_text(kind, note, timestamp):
    """Render one staged note as a durable entry, per data-model.md's fields."""
    title, body = _title_and_body(note)
    fields = ["captured_at: " + timestamp, "category: " + kind]
    if kind == "task":
        status, body = _split_status(body)
        fields.append("status: " + (status or DEFAULT_TASK_STATUS))

    label = ENTRY_HEADING[kind]
    # CONTINUI-50: a note titled "Decision: X" must not become "Decision: Decision: X".
    if title.lower().startswith(label.lower() + ":"):
        title = title[len(label) + 1 :].strip() or "untitled"
    lines = ["## {}: {}".format(label, title), "", "```"]
    lines.extend(fields)
    lines.extend(["```", ""])
    lines.extend(_demote_headings(body))
    return "\n".join(lines).rstrip() + "\n"


def _title_and_body(note):
    """Split a staged note into an entry title and its body.

    A note whose first line is a Markdown heading gives up that line as the
    title; any other note keeps its full text as the body and borrows its
    opening words as a title, so no content is ever dropped to make a title.
    """
    lines = note.splitlines()
    index = 0
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        return "untitled", ""

    first = lines[index].strip()
    if first.startswith("#"):
        title = first.lstrip("#").strip() or "untitled"
        body = "\n".join(lines[index + 1 :]).strip()
        return title[:TITLE_MAX].rstrip(), body

    titled = _TITLE_LINE.match(first)
    if titled:
        # Agents often open a note with `title: X` instead of a Markdown heading.
        return titled.group(1)[:TITLE_MAX].rstrip(), "\n".join(lines[index + 1 :]).strip()

    return first[:TITLE_MAX].rstrip(), "\n".join(lines[index:]).strip()


def _demote_headings(body):
    """Push body headings two levels down.

    A `##` line inside a body would otherwise read as the start of the next
    entry to every parser built against
    contracts/file-format-contract.md's entry rule.
    """
    return ["##" + line if line.startswith("#") else line for line in body.splitlines()]


def _append_entries(continuity_dir_path, filename, texts):
    target = os.path.join(continuity_dir_path, filename)
    existing = _read(target) or ""
    if existing and not existing.endswith("\n"):
        existing += "\n"
    if existing.strip():
        existing += "\n"

    try:
        atomic_write(target, existing + "\n".join(texts))
    except OSError as error:
        continuity_log(
            continuity_dir_path,
            "write-" + filename.replace(".md", ""),
            "write-failed",
            type(error).__name__,
        )


def _split_status(body):
    """Return (status, body-without-the-status-line).

    The first `status: active|blocked|done` line in a task note is its status;
    an unrecognized value is left in the body and the status stays unset.
    """
    status = None
    kept = []
    for line in body.splitlines():
        match = _STATUS_LINE.match(line)
        if status is None and match and match.group(1).lower() in TASK_STATUSES:
            status = match.group(1).lower()
            continue
        kept.append(line)
    return status, "\n".join(kept).strip()


def _task_key(heading_title):
    title = heading_title.strip()
    if title.lower().startswith("task:"):
        title = title[len("task:") :].strip()
    return title.lower()


def _split_entries(text):
    """Return (head, entries): head is the text before the first `## ` line and
    each entry is one `## ` block. Body headings are demoted on write, so a
    `## ` line is always an entry's own heading."""
    head, entries, current = [], [], None
    for line in text.splitlines():
        if line.startswith("## "):
            current = [line]
            entries.append(current)
        elif current is None:
            head.append(line)
        else:
            current.append(line)
    return "\n".join(head), ["\n".join(entry) for entry in entries]


def _update_task_entry(entry, status, timestamp, body):
    """Mutate one task entry in place: new status, `updated_at`, and the new body
    when the note brought one. Returns None if the entry has no field block."""
    lines = entry.splitlines()
    fences = [i for i, line in enumerate(lines) if line.strip().startswith("```")]
    if len(fences) < 2:
        return None
    start, end = fences[0], fences[1]
    old_status = None
    fields = []
    for line in lines[start + 1 : end]:
        key = line.split(":", 1)[0].strip()
        if key == "status":
            old_status = line.split(":", 1)[1].strip()
        elif key != "updated_at":
            fields.append(line)
    fields.append("status: " + (status or old_status or DEFAULT_TASK_STATUS))
    fields.append("updated_at: " + timestamp)
    old_body = "\n".join(lines[end + 1 :]).strip()
    new_body = body if body else old_body
    out = [lines[0], "", "```"] + fields + ["```", ""] + new_body.splitlines()
    return "\n".join(out).rstrip() + "\n"


def _upsert_tasks(continuity_dir_path, notes, timestamp):
    """Apply task notes to tasks.md: same title updates that entry in place
    (data-model.md: "status transitions in place"), a new title appends."""
    target = os.path.join(continuity_dir_path, "tasks.md")
    try:
        head, entries = _split_entries(_read(target) or "")
        index = {}
        for position, entry in enumerate(entries):
            index[_task_key(entry.splitlines()[0][3:])] = position
        for note in notes:
            title, body = _title_and_body(note)
            key = _task_key(title)
            status, body = _split_status(body)
            position = index.get(key)
            updated = (
                _update_task_entry(entries[position], status, timestamp, body)
                if position is not None
                else None
            )
            if updated is not None:
                entries[position] = updated
            else:
                entries.append(_entry_text("task", note, timestamp))
                index[key] = len(entries) - 1
        text = (head.rstrip() + "\n\n" if head.strip() else "") + "\n".join(
            entry.rstrip("\n") + "\n" for entry in entries
        )
        atomic_write(target, text)
    except Exception as error:  # noqa: BLE001 — never lose a note to a parse bug
        continuity_log(
            continuity_dir_path, "write-tasks", "write-failed", type(error).__name__
        )
        _append_entries(
            continuity_dir_path, "tasks.md", [_entry_text("task", n, timestamp) for n in notes]
        )


def _state_parts(lines):
    """Split lines into (summary, constraints) at a `Constraints` heading or label."""
    summary, constraints = [], []
    target = summary
    for line in lines:
        label = line.strip().lstrip("#").strip().lower().rstrip(":")
        if label == "constraints":
            target = constraints
            continue
        target.append(line)
    return summary, constraints


def _trim_blank(lines):
    lines = list(lines)
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _write_state(continuity_dir_path, notes, timestamp):
    """Rewrite state.md in place from the newest state note (data-model.md: one
    current state, superseded not accumulated). A part the note omits keeps its
    previous value, and the file is never reduced to empty. Returns True if written."""
    target = os.path.join(continuity_dir_path, STATE_FILE)
    old_summary, old_constraints = [], []
    old = _read(target)
    if old:
        lines = old.splitlines()
        fences = [i for i, line in enumerate(lines) if line.strip().startswith("```")]
        body = lines[fences[1] + 1 :] if len(fences) >= 2 else []
        old_summary, old_constraints = _state_parts(body)

    note_lines = notes[-1].splitlines()
    while note_lines and not note_lines[0].strip():
        note_lines.pop(0)
    if note_lines and note_lines[0].lstrip().startswith("#") and "constraints" not in note_lines[0].lower():
        note_lines.pop(0)
    summary, constraints = _state_parts(note_lines)
    summary, constraints = _trim_blank(summary), _trim_blank(constraints)
    if not summary and not constraints:
        # Nothing new: leave state.md and its updated_at exactly as they were.
        continuity_log(
            continuity_dir_path, "write-state", "empty", "state note had no content"
        )
        return False
    summary = summary or _trim_blank(old_summary)
    constraints = constraints or _trim_blank(old_constraints)

    text = "\n".join(
        [STATE_HEADING, "", "```", "updated_at: " + timestamp, "```", ""]
        + (summary + [""] if summary else [])
        + ["## Constraints", ""]
        + (constraints + [""] if constraints else [])
    )
    try:
        atomic_write(target, text.rstrip("\n") + "\n")
    except OSError as error:
        continuity_log(
            continuity_dir_path, "write-state", "write-failed", type(error).__name__
        )
        return False
    return True


def _write_handoff(continuity_dir_path, trigger_kind, timestamp, body, counts):
    """Write one sessions/<timestamp>-<pid>.md handoff. Returns its path or None."""
    if not body:
        # No staged handoff note: state what was consolidated as plain fact.
        # Composing a summary would be prose, which this script never writes.
        written = ", ".join(
            "{} {}".format(count, kind) for kind, count in sorted(counts.items()) if count
        )
        body = "Consolidated: " + (written or "nothing new")

    target = os.path.join(
        continuity_dir_path,
        SESSIONS_DIRNAME,
        "{}-{}.md".format(_filename_timestamp(), os.getpid()),
    )
    text = "```\ncaptured_at: {}\ntrigger: {}\n```\n\n{}\n".format(
        timestamp, trigger_kind, body.strip()
    )

    try:
        atomic_write(target, text)
    except OSError as error:
        continuity_log(
            continuity_dir_path, "write-handoff", "write-failed", type(error).__name__
        )
        return None
    return target


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _filename_timestamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main(argv=None):
    """CLI entry point. Always exits 0 — a trigger must never see a failure."""
    parser = argparse.ArgumentParser(
        description="Consolidate staged Continuity notes into a project's store."
    )
    parser.add_argument("cwd", help="absolute path of the project root")
    parser.add_argument("trigger_kind", help="which signal produced this run")
    args = parser.parse_args(argv)

    try:
        handoff_path = write_memory(args.cwd, args.trigger_kind)
    except Exception as error:  # fail open: a detached writer has no one to raise to
        continuity_log(
            continuity_dir(args.cwd), "write-memory", "write-failed", type(error).__name__
        )
        handoff_path = None

    if handoff_path:
        print("Checkpoint written to " + handoff_path)
    else:
        print("Nothing new to checkpoint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
