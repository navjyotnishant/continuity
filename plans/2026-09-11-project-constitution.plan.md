# Plan: Write the project constitution

**Approved**: yes — by explicit, fully-specified user instruction in this
session (the user dictated exact principle text, sourcing, and section
structure, and said "Commit the file").

## Goal
Populate `.specify/memory/constitution.md` (spec-kit's read target for every
later stage: spec, plan, tasks, implementation) with the governance rules
this repository has already decided, each citing its source, replacing every
template placeholder. Invent nothing left open by the intent doc.

## Scope
- Write exactly one file: `.specify/memory/constitution.md`.
- No application code, no other docs, no template files under
  `.specify/templates/` are touched.

## Sources (already decided, not invented here)
- `orion.json` → `vcs`, `gates.*`: branch model, plan-before-edit,
  protect-tests-during-fix, production-requires-authorization,
  no-direct-push-to-default-branch.
- `docs/intent/continuity.md` → Constraints + answered Open Questions:
  claude-plugin-only distribution via a GitHub marketplace, no
  server/database/cloud/Go dependency for the MVP, no per-interaction LLM
  memory writes, no full-conversation replay into a new session, fail-open
  on any Continuity failure.

## Steps
1. Read `docs/intent/continuity.md` and `orion.json` to confirm sourcing (done).
2. Read the existing `.specify/memory/constitution.md` template scaffold to
   know which placeholders must be replaced (done).
3. Write the five core principles (branch model, plan-before-edit,
   protect-tests-during-fix, production-authorization, no-direct-push),
   an Additional Constraints section for the intent's constraints, and a
   Governance section — each citing its source inline. Drop the template's
   third generic section rather than fill it with invented content.
4. Set version 1.0.0 (initial adoption), Ratified/Last Amended = today.
5. Commit the file with a `docs:` commit message.

## Risks / non-goals
- Does not settle anything the intent left open beyond what it already
  answered (e.g. storage format stays "Markdown files under `.continuity/`"
  as already decided, not expanded on).
- Does not modify `orion.json`, spec-kit templates, or any other artifact.
