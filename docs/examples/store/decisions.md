# Decisions

Append-only, oldest first. One entry per decision, with the reasoning behind
it, so it does not get re-litigated in a later session.

## Decision: Parse with recursive descent

```
captured_at: 2026-09-14T09:00:00Z
category: decision
```

A hand-written recursive-descent parser is enough for + - * / and parentheses, and avoids a parser-generator dependency (standard library only).

## Decision: Unary minus binds tighter than multiplication

```
captured_at: 2026-09-15T10:30:00Z
category: decision
```

So `-2*3` is `(-2)*3`, as on common calculators, and the grammar stays unambiguous.
