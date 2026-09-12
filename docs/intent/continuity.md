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
- [x] What specifically counts as "context" to persist (decisions, facts about
  the user, code/file history, preferences, all of the above)? Not stated.
  Answer: For Continuity, **“context” means the project information that would materially help a future or concurrent Claude Code session understand and continue the work without repeating the previous session**. This includes important architectural and implementation decisions, stable facts about the project, the current state of the work, active or unfinished tasks, known constraints, discoveries and learnings, established conventions, and relevant session handoffs. It does not mean storing or replaying the entire conversation; transient debugging, repeated explanations, routine tool activity, and other information with little future value should generally not become persistent context. The goal is to preserve the **state and knowledge of the work**, so another session can pick up where the project actually stands.
- [x] What storage mechanism satisfies "no database installation requirement"
  and "no separate server" — is a plain file/directory acceptable, and does
  an embedded (no-install) database count as a "database" for this
  constraint? Not stated.
  Answer: For the MVP, use **project-local Markdown/text files under `.continuity/`**. This satisfies the **“no database installation requirement”** while keeping the memory human-readable, portable, Git-friendly, and easy to inspect or recover. We can start with structured files such as `state.md`, `decisions.md`, `tasks.md`, and `learnings.md`, and only introduce a local embedded store such as SQLite later if retrieval or concurrency requirements prove that files alone are insufficient.
- [x] Is continuity scoped per-project, per-user across all projects, or both?
  Not stated.
  Answer: **Continuity should be primarily scoped per-project, with optional per-user/global context later.** The MVP should keep the persistent project context under the project root in `.continuity/`, so each repository maintains its own state, decisions, tasks, constraints, and learnings. A future version could add a separate user-level memory layer for preferences or coding habits that should apply across projects, but that should remain separate from project continuity.
- [x] What triggers a memory write, if not every interaction (end of session, an
  explicit save, a periodic checkpoint)? Not stated.
  Answer: **Memory writes should be triggered by meaningful changes in project state rather than every interaction.** For the MVP, Continuity should use lightweight signals such as significant file changes, meaningful git diffs, completed or changed tasks, important decisions, test milestones, and explicit session checkpoints. A `SessionEnd` event can trigger a final checkpoint, but it should not be the only trigger because another session may need the context while the first session is still active. The write should happen asynchronously so it never blocks the developer’s Claude Code interaction.
- [x] Is there a quantified latency/performance budget, or is "feels exactly as
  fast" the only bar, to be judged subjectively? Not stated.
  Answer: For the MVP, **“feels exactly as fast” should be the qualitative product requirement**, rather than imposing an arbitrary hard latency number before we understand Claude Code’s hook behavior. Continuity must not block or noticeably delay Claude Code’s interactive workflow. Background capture and memory processing should be asynchronous, and any `SessionStart` context loading should be lightweight enough that the user does not perceive a meaningful difference. Once the MVP is implemented, we should **measure the actual overhead** and establish quantitative performance targets based on those results.
- [x] How does Continuity detect its own failure in order to degrade gracefully,
  and what counts as "failure" (read error, write error, corrupted memory
  file)? Not stated.
  Answer: Continuity should use **simple health checks and fail-open behavior**. Each operation should have clear success/failure handling, such as verifying that `.continuity/` exists and is readable/writable, checking that state files are valid before using them, and detecting timeouts or errors from background processing. If any Continuity operation fails, the plugin should **log the failure locally and skip the continuity operation rather than interrupting Claude Code**. The key principle is that failure should be isolated: **Continuity can become unavailable, but it must never prevent Claude Code from continuing normally.**
- [x] Which Claude Code plugin marketplace is the distribution target? Not
  stated.
  Answer: github repo

---

Captured: 2026-09-11
Author: Navjyot Nishant
