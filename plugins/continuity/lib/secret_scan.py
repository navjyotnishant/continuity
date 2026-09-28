"""lib/secret_scan.py — the regex gate every persisted line passes through.

research.md R5: a small fixed set of `re` patterns, run over content on its
way into a durable file. This is a *mitigation*, not a guarantee (plan.md's
Risks says so plainly, and docs/install.md must repeat it): it exists because
`.continuity/` is git-tracked by default (Q1), so a pasted credential would
otherwise reach shared history before anyone noticed.

Callers log only the returned pattern *name* — never the matched text
(data-model.md's Failure Log Entry rule).

Standard library only (Python 3.9+) — no third-party imports, ever.
"""

import re

PATTERNS = (
    ("aws-key-pattern", re.compile(r"\b(?:A3T[A-Z0-9]|AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}\b")),
    (
        "assignment-pattern",
        re.compile(
            r"(?i)\b(?:api[_-]?key|key|token|secret|password|passwd|access[_-]?key)\b"
            r"\s*[:=]\s*\S{6,}"
        ),
    ),
    ("pem-private-key", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    (
        "high-entropy-run",
        re.compile(r"\b(?=[A-Za-z0-9+/]*[0-9])(?=[A-Za-z0-9+/]*[A-Za-z])[A-Za-z0-9+/]{40,}={0,2}"),
    ),
)


def secret_scan_line(text):
    """Return the name of the first pattern `text` matches, else None.

    A None return means "safe to persist"; any string return means the
    caller drops that line and logs `secret-blocked` with this name as the
    only detail.
    """
    for name, pattern in PATTERNS:
        if pattern.search(text):
            return name
    return None
