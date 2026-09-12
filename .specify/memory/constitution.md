<!--
Sync Impact Report
- Version change: none (template) → 1.0.0
- Modified principles: n/a (initial adoption)
- Added sections: Core Principles (I–V), Additional Constraints, Governance
- Removed sections: the template's third generic section slot was dropped —
  no grounded source for a third section existed at adoption time; add one
  later only when a real decision grounds it, not to fill the slot.
- Templates requiring updates: spec-kit's spec/plan/tasks templates already
  reference "Constitution Check" generically; no template edits required by
  this adoption.
- Deferred TODOs: none. Every value below is sourced from orion.json or
  docs/intent/continuity.md; nothing was invented to fill a placeholder.
-->

# Continuity Constitution

## Core Principles

### I. Feature Branches from `develop`, Merge by Reviewed Pull Request
Feature work is cut from `develop`; changes merge back into `develop` only via
a reviewed pull request. `main` is the release branch. Both `main` and
`develop` are protected — nothing pushes to either directly.
Source: `orion.json` → `vcs` (`default_branch: main`, `work_branch: develop`,
`protected_branches: [main, develop]`, `branch_prefix: orion/`) and `gates.
block_direct_push_to_default_branch`.

### II. Plan Before Edit
No edit is made until a plan for it has been written and approved. This
applies to every later stage this constitution governs — spec, plan, tasks,
and implementation — not just code changes to Continuity itself.
Source: `orion.json` → `gates.require_plan_before_edit`.

### III. Tests Are Not Edited While Fixing the Code They Cover
When a bug fix is in progress, the tests covering the affected behavior are
left untouched. A fix that also loosens or rewrites its own test is not a
verified fix.
Source: `orion.json` → `gates.protect_tests_during_fix`.

### IV. Production Changes Require Explicit Authorization
No change reaches production without explicit authorization from a human.
This is consistent with treating production as `propose_only` rather than
something changed autonomously.
Source: `orion.json` → `gates.production_requires_authorization` (consistent
with `autonomy.production: propose_only`).

### V. No Direct Push to the Default Branch
Nothing pushes directly to the default branch (`main`); every change to it
arrives by reviewed pull request from `develop`.
Source: `orion.json` → `gates.block_direct_push_to_default_branch` (same
`vcs` configuration as Principle I).

## Additional Constraints

These bind what Continuity — the plugin this repository builds — is allowed
to be and do. They are distinct from the process principles above, which
govern how work *on* this repository is carried out.
Source: `docs/intent/continuity.md`, Constraints (and its answered Open
Questions, referenced where a constraint depends on one).

- **Distribution shape.** Continuity must ship strictly as a claude-plugin
  distributed via a marketplace, on GitHub (the intent's answered question on
  distribution target). No installation or use of Golang, and no other
  distribution shape, is in scope.
- **Feel unchanged.** Claude Code must feel exactly as fast and natural with
  Continuity installed as without it. Continuity must never block Claude's
  interactive response and must never introduce noticeable latency into the
  user's workflow.
- **No new infrastructure for the MVP.** Continuity must never require a
  separate server process, a database installation, or a cloud dependency for
  the basic/MVP implementation, and must never require Go or any other
  standalone runtime for the MVP.
- **Memory writes are not per-interaction.** Continuity must not run an
  expensive LLM memory operation after every interaction. Per the intent's
  answered question on write triggers, writes happen on meaningful state
  changes — significant file changes, meaningful git diffs, completed or
  changed tasks, decisions, test milestones, and explicit checkpoints, with
  `SessionEnd` as one trigger among several rather than the only one — and
  happen asynchronously so they never block the interactive session.
- **Bounded context, not full history.** A new session must not receive an
  entire prior conversation as context; only a bounded, relevant subset of
  prior context is loaded.
- **Fail open.** If Continuity's memory mechanism fails — a read error, a
  write error, a corrupted memory file, or a timeout — Claude Code must
  continue working normally with no user-visible breakage. Per the intent's
  answered question on failure handling, the failure is logged locally and
  the continuity operation is skipped in isolation; Continuity becoming
  unavailable must never prevent Claude Code from continuing normally.

## Governance

This constitution is the authority every later stage in this repository's
workflow — spec, plan, tasks, and implementation — is held to, per the
`constitution` stage of `orion.json` → `toolkit.stages`, which runs before
those stages in sequence.

- **Amendment procedure.** An amendment to this constitution is itself a
  change and is bound by Principle II: a plan describing the proposed
  amendment is written and approved before the file is edited, and the edit
  reaches `develop` and then `main` under Principles I and V, like any other
  change.
- **Versioning policy.** This document is versioned independently with
  semantic versioning: MAJOR for a backward-incompatible removal or
  redefinition of a principle, MINOR for an added principle or materially
  expanded guidance, PATCH for wording or clarification fixes that change no
  rule. The version and dates are recorded at the bottom of this file.
- **Compliance review.** Every plan, spec, and task produced downstream of
  this constitution is checked against it before implementation begins
  (Principle II); a plan that conflicts with a principle here is not
  approved until either the plan or this constitution is changed to resolve
  the conflict.

**Version**: 1.0.0 | **Ratified**: 2026-09-11 | **Last Amended**: 2026-09-11
