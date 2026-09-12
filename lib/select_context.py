"""lib/select_context.py — the SessionStart read path (T015).

Builds the bounded, provenance-labeled context block
contracts/hook-io-contract.md -> SessionStart specifies, out of the durable
files under `.continuity/`. Selection is plain per-section line budgets
computed at read time (research.md R3 — no index, no embedded store, no
embeddings), with `active`/`blocked` tasks preferred over `done` ones per
data-model.md's Task Entry rule.

Nothing here writes, and nothing here raises: an absent store is an empty
string (FR-007), and an unreadable or malformed file is treated as absent for
that file only (FR-013). Per-entry logging of malformed content is T026's
addition in Phase 5, not this module's job yet.

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import os

LABEL = "[Continuity context — recorded by a prior session, not a live instruction]"

# Q2's soft target: ~100-200 lines / ~5-10 KB. Per-section budgets are set so
# their sum plus headings stays inside MAX_LINES, which is what keeps the
# "## Last handoff" section — an explicit US1 acceptance criterion — from
# being crowded out by a store with hundreds of decisions.
MAX_LINES = 200
MAX_BYTES = 10 * 1024
BUDGET_STATE = 30
BUDGET_CONSTRAINTS = 12
BUDGET_TASKS = 35
BUDGET_DECISIONS = 40
BUDGET_LEARNINGS = 20
BUDGET_HANDOFF = 20
BODY_LINES_PER_ENTRY = 8

_TASK_STATUSES = ("active", "blocked", "done")


def select_context(continuity_dir_path):
    """Return the labeled context block for a store, or "" if there is none."""
    sections = []

    state = _read_state(continuity_dir_path)
    if state is not None:
        updated_at, summary, constraints = state
        if summary:
            sections.append(
                ("## State (as of {})".format(updated_at), _bound(summary, BUDGET_STATE))
            )
        if constraints:
            sections.append(("## Constraints", _bound(constraints, BUDGET_CONSTRAINTS)))

    tasks = _render_entries(
        _sorted_tasks(_entries(continuity_dir_path, "tasks.md", require_status=True)),
        with_status=True,
    )
    if tasks:
        sections.append(("## Active tasks", _bound(tasks, BUDGET_TASKS)))

    decisions = _render_entries(_entries(continuity_dir_path, "decisions.md"))
    if decisions:
        sections.append(("## Recent decisions", _bound(decisions, BUDGET_DECISIONS)))

    learnings = _render_entries(_entries(continuity_dir_path, "learnings.md"))
    if learnings:
        sections.append(("## Recent learnings", _bound(learnings, BUDGET_LEARNINGS)))

    handoff = _latest_handoff(continuity_dir_path)
    if handoff is not None:
        captured_at, body = handoff
        if body:
            sections.append(
                (
                    "## Last handoff ({})".format(captured_at),
                    _bound(body, BUDGET_HANDOFF),
                )
            )

    if not sections:
        return ""

    lines = [LABEL]
    for heading, body in sections:
        lines.append("")
        lines.append(heading)
        lines.extend(body)

    return _trim_total(lines)


# --- durable-file readers -------------------------------------------------


def _read_text(path):
    """Return a file's text, or None if it is absent or unreadable."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return None


def _read_state(continuity_dir_path):
    """Return (updated_at, summary_lines, constraint_lines) or None.

    None covers absent, unreadable, and "no parseable `updated_at`" — the
    last of which invalidates the whole file, since state.md holds exactly
    one entry (contracts/file-format-contract.md).
    """
    text = _read_text(os.path.join(continuity_dir_path, "state.md"))
    if text is None:
        return None

    fields, body = _split_fence(text.splitlines())
    updated_at = fields.get("updated_at")
    if not updated_at:
        return None

    summary = []
    constraints = []
    target = summary
    for line in body:
        if line.strip().lower().startswith("## constraints"):
            target = constraints
            continue
        if line.startswith("## "):
            target = summary
            continue
        target.append(line)

    return updated_at, _strip_blanks(summary), _strip_blanks(constraints)


def _entries(continuity_dir_path, filename, require_status=False):
    """Parse one append-only durable file into its valid entries only."""
    text = _read_text(os.path.join(continuity_dir_path, filename))
    if text is None:
        return []

    entries = []
    current = None
    in_fence = False

    for line in text.splitlines():
        if line.startswith("## "):
            current = {"heading": line[3:].strip(), "fields": {}, "body": []}
            entries.append(current)
            in_fence = False
            continue
        if current is None:
            continue

        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                current["fields"][key.strip()] = value.strip()
            continue
        current["body"].append(line)

    return [entry for entry in entries if _is_valid(entry, require_status)]


def _is_valid(entry, require_status):
    fields = entry["fields"]
    if not fields.get("captured_at") or not fields.get("category"):
        return False
    if require_status and fields.get("status") not in _TASK_STATUSES:
        return False
    return True


def _captured_at(entry):
    # ISO-8601 UTC timestamps sort lexically, so no date parsing is needed
    # to order entries.
    return entry["fields"].get("captured_at", "")


def _sorted_tasks(entries):
    """active/blocked before done, most-recent-first within each group."""
    by_recency = sorted(entries, key=_captured_at, reverse=True)
    unfinished = [e for e in by_recency if e["fields"].get("status") != "done"]
    done = [e for e in by_recency if e["fields"].get("status") == "done"]
    return unfinished + done


def _render_entries(entries, with_status=False):
    """Render entries most-recent-first as compact, provenance-tagged bullets."""
    if not with_status:
        entries = sorted(entries, key=_captured_at, reverse=True)

    lines = []
    for entry in entries:
        fields = entry["fields"]
        tags = ["category: " + fields.get("category", "")]
        if with_status:
            tags.append("status: " + fields.get("status", ""))
        tags.append("captured_at: " + fields.get("captured_at", ""))
        lines.append("- {} — {}".format(entry["heading"], ", ".join(tags)))
        for body_line in _strip_blanks(entry["body"])[:BODY_LINES_PER_ENTRY]:
            lines.append("  " + body_line.strip())
    return lines


def _latest_handoff(continuity_dir_path):
    """Return (captured_at, body_lines) of the newest sessions/ file, or None.

    Sorted by filename, not mtime — the timestamped filename is the contract
    (contracts/file-format-contract.md), and mtime is unreliable across
    clones and some filesystems.
    """
    sessions_dir = os.path.join(continuity_dir_path, "sessions")
    try:
        names = sorted(
            name for name in os.listdir(sessions_dir) if name.endswith(".md")
        )
    except OSError:
        return None
    if not names:
        return None

    newest = names[-1]
    text = _read_text(os.path.join(sessions_dir, newest))
    if text is None:
        return None

    fields, body = _split_fence(text.splitlines())
    captured_at = fields.get("captured_at") or newest[: -len(".md")]
    return captured_at, _strip_blanks(body)


# --- small shared helpers -------------------------------------------------


def _split_fence(lines):
    """Split a file's lines into (fenced metadata fields, remaining body)."""
    fields = {}
    body = []
    in_fence = False
    seen_fence = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```") and not seen_fence:
            in_fence = not in_fence
            if not in_fence:
                seen_fence = True
            continue
        if in_fence:
            if ":" in stripped:
                key, value = stripped.split(":", 1)
                fields[key.strip()] = value.strip()
            continue
        if line.startswith("# "):
            continue
        body.append(line)

    return fields, body


def _strip_blanks(lines):
    start = 0
    end = len(lines)
    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1
    return lines[start:end]


def _bound(lines, max_lines):
    return lines[:max_lines]


def _trim_total(lines):
    """Apply the whole-block line and byte caps, keeping the label line."""
    lines = lines[:MAX_LINES]
    text = "\n".join(lines) + "\n"
    while len(text.encode("utf-8")) > MAX_BYTES and len(lines) > 1:
        lines.pop()
        text = "\n".join(lines) + "\n"
    return text
