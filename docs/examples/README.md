# What Continuity writes: an example

A small project, `toy-calc`, over two sessions. [`staged-notes/`](staged-notes/) holds the
notes an agent writes (one file per note); [`store/`](store/) is what Continuity's
writer turns them into. `store/` is generated from `staged-notes/` by the real writer
and checked by a test, so it cannot drift from what the code does.

## Session 1

| Note the agent stages | Lands in |
|---|---|
| [`decision-1.md`](staged-notes/run-1/decision-1.md) | a new entry in [`decisions.md`](store/decisions.md) |
| [`learning-1.md`](staged-notes/run-1/learning-1.md) | a new entry in [`learnings.md`](store/learnings.md) |
| [`task-1.md`](staged-notes/run-1/task-1.md), `status: active` | a new task, active |
| [`task-2.md`](staged-notes/run-1/task-2.md), `status: blocked` | a new task, blocked |
| [`state-1.md`](staged-notes/run-1/state-1.md) | [`state.md`](store/state.md): the summary and the `Constraints` section |
| [`handoff-1.md`](staged-notes/run-1/handoff-1.md) | a file in [`sessions/`](store/sessions/) |

## Session 2

| Note the agent stages | What happens |
|---|---|
| [`task-1.md`](staged-notes/run-2/task-1.md), same title, `status: done` | the lexer task is **updated in place**: status `done`, an `updated_at` is added, `captured_at` is kept |
| [`task-2.md`](staged-notes/run-2/task-2.md), same title, `status: active` | the parser task moves from blocked to active, also in place |
| [`decision-1.md`](staged-notes/run-2/decision-1.md) | appended: decisions are a history, never edited |
| [`state-1.md`](staged-notes/run-2/state-1.md), no constraints | `state.md` is **replaced**, not appended; the constraints it did not mention are kept |
| [`handoff-1.md`](staged-notes/run-2/handoff-1.md) | a second file in `sessions/` |

## The rules, in short

- **Decisions and learnings** are append-only. Each note becomes one entry.
- **Tasks** carry a `status` of `active`, `blocked` or `done`. A note with the same
  title as an existing task updates it in place. Open tasks are recalled before done ones.
- **State** is one current summary plus constraints. A new state note replaces it; a part
  the note leaves out keeps its previous value, and an empty note changes nothing.
- **Session handoffs** are one file per session and are cleaned up after 60 days.
- A note's first line (`# Title`) becomes the entry title. Secret-looking lines are
  dropped before anything is written.

At the start of the next session Continuity shows the agent a bounded summary of these
files: state and constraints, open tasks, recent decisions and learnings, and the last
handoff.

To regenerate `store/` after changing the writer or the notes:

```sh
python3 plugins/continuity/tests/example_store.py --write
```
