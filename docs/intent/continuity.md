# Continuity

## Intent

For anyone using Claude Code for development or any other work: memory from
one session is not available in another session, so context gets reset each
time — it feels like talking to someone unknown. Continuity should make
cross-session context available, so that isn't the experience.

It must ship strictly as a claude-plugin distributed via a marketplace — no
installation or use of Golang.

## Why now

Not stated.

## Constraints

- Claude Code must feel exactly as fast and natural with Continuity installed
  as it does without Continuity.
- Never block Claude's interactive response.
- Never introduce noticeable latency into the user's workflow.
- Never require a separate server.
- Do not run an expensive LLM memory operation after every interaction.
- Do not load entire previous conversations into a new session.
- If Continuity fails, Claude Code must continue working normally.
- No database installation requirement.
- No cloud dependency for the basic implementation.
- Never require Go or another standalone runtime for the MVP.

## Out of scope

- Any installation or use of Golang.
- Anything that isn't a claude-plugin distributed via a marketplace.

## Success measures
- A new Claude Code session references relevant facts or decisions from a
  prior session without the user having to re-explain them.
- Interactive response latency with Continuity installed matches latency
  without it closely enough that a user doing normal work does not notice a
  difference.
- No per-interaction step runs an expensive LLM memory operation — memory
  writes happen on some other cadence, not every message.
- A new session does not receive the entire prior conversation as context —
  only a bounded, relevant subset.
- Installing Continuity requires no separate server process, no database
  installation, no cloud account/dependency, and no Go or other standalone
  runtime — just the claude-plugin installed via a marketplace.
- If Continuity's memory mechanism fails (errors, is unavailable, or is
  corrupted), Claude Code continues working normally with no user-visible
  breakage.

## Open questions
- What specifically counts as "context" to persist (decisions, facts about
  the user, code/file history, preferences, all of the above)? Not stated.
- What storage mechanism satisfies "no database installation requirement"
  and "no separate server" — is a plain file/directory acceptable, and does
  an embedded (no-install) database count as a "database" for this
  constraint? Not stated.
- Is continuity scoped per-project, per-user across all projects, or both?
  Not stated.
- What triggers a memory write, if not every interaction (end of session, an
  explicit save, a periodic checkpoint)? Not stated.
- Is there a quantified latency/performance budget, or is "feels exactly as
  fast" the only bar, to be judged subjectively? Not stated.
- How does Continuity detect its own failure in order to degrade gracefully,
  and what counts as "failure" (read error, write error, corrupted memory
  file)? Not stated.
- Which Claude Code plugin marketplace is the distribution target? Not
  stated.

---

Captured: 2026-09-11
Author: Navjyot Nishant
