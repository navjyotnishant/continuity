# Learnings

Append-only, oldest first. Discoveries worth not re-making, plus the
established conventions of this project.

## Learning: str.split keeps empty fields

```
captured_at: 2026-09-14T09:00:00Z
category: learning
```

`'1,,2'.split(',')` returns `['1', '', '2']`, so the tokenizer must skip empty strings.
