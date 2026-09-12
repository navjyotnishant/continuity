# Feature Specification: Continuity

**Feature Branch**: `001-continuity`

**Created**: 2026-09-12

**Status**: Draft

**Input**: User description: "Continuity: a claude-plugin (distributed via a GitHub marketplace, no Go, no server, no database install, no cloud dependency) that gives Claude Code cross-session memory. It must persist project-scoped context (decisions, stable facts, current state, active tasks, constraints, learnings, session handoffs) under .continuity/ as Markdown/text files, load a bounded relevant subset of that context at SessionStart with no noticeable latency, write memory asynchronously on meaningful-change triggers (not every interaction, not only SessionEnd) so it never blocks the interactive response, and fail open (skip + log locally) on any read/write/corruption error so Claude Code keeps working normally. Full intent doc at docs/intent/continuity.md."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Resume a project without re-explaining it (Priority: P1)

A developer returns to a project in a brand-new Claude Code session — a new
terminal, a new day, or after a context reset — and Claude already knows the
project's current state, the decisions already made, the constraints already
agreed to, and what was left unfinished, without the developer re-typing any
of it.

**Why this priority**: This is the entire reason Continuity exists (see
`docs/intent/continuity.md` → Intent). Every other requirement exists to make
this happen safely and without cost.

**Independent Test**: Work a session to a natural stopping point on a project
with Continuity installed (make at least one decision, leave one task
unfinished), end the session, start a brand-new session on the same project,
and confirm the new session's opening context includes that decision and that
unfinished task without the developer restating them.

**Acceptance Scenarios**:

1. **Given** a project with prior Continuity history recorded under
   `.continuity/`, **When** a new Claude Code session starts on that project,
   **Then** the session's opening context includes the still-relevant
   decisions, active tasks, constraints, and the most recent session handoff,
   without the developer having to ask for them.
2. **Given** a decision was recorded in a previous session, **When** the
   developer asks a question in the new session that depends on that
   decision, **Then** Claude answers consistently with the recorded decision
   instead of re-deriving or contradicting it.
3. **Given** a project that has never had a Continuity session before,
   **When** a new session starts, **Then** the session proceeds normally with
   no continuity context injected and no error surfaced.

---

### User Story 2 - Never notice Continuity is running (Priority: P1)

A developer working normally — asking questions, editing files, running
commands — perceives no difference in Claude Code's responsiveness whether
Continuity is installed or not, and never has to wait on a memory operation.

**Why this priority**: Per `docs/intent/continuity.md` → Constraints, this is
a hard product bar, not a nice-to-have: a memory feature that is felt is a
feature that gets uninstalled. It is equally load-bearing as User Story 1.

**Independent Test**: Time a representative sequence of interactive turns
(file edits, questions, tool calls) on the same project once with Continuity
installed and once without, and confirm a developer performing normal work
cannot distinguish the two by feel; confirm no turn is observed waiting on a
memory write or an LLM-based memory summarization step before Claude
responds.

**Acceptance Scenarios**:

1. **Given** Continuity is installed and active, **When** the developer sends
   an interactive message that would otherwise trigger a memory-write signal
   (e.g., a meaningful file change), **Then** Claude's response to that
   message is not delayed waiting for the memory write to finish.
2. **Given** a long interactive session with many turns, **When** memory
   writes occur in the background, **Then** no individual turn incurs an
   additional LLM call solely to summarize or persist memory.
3. **Given** a new session is starting, **When** Continuity loads its bounded
   context subset, **Then** the additional session-start time is not
   perceptible to the developer compared to starting without Continuity.

---

### User Story 3 - Keep working when memory breaks (Priority: P2)

A developer's `.continuity/` store becomes unreadable, corrupted, or is
simply missing (fresh clone, deleted folder, a bad manual edit, a disk/
permission error), and Claude Code continues to work exactly as it would
without Continuity at all — no crash, no blocking error, no degraded
interactive behavior.

**Why this priority**: Per `docs/intent/continuity.md` → Constraints
("Continuity can become unavailable, but it must never prevent Claude Code
from continuing normally"), this is the safety property that makes it
acceptable to ship a memory feature with no server, no database, and no
transactional guarantees. It is secondary to the core value (P1) but is what
makes P1 safe to ship.

**Independent Test**: Deliberately corrupt or remove `.continuity/` content
(truncate a file mid-write, replace a file with invalid content, remove read
permission, delete the directory entirely) and confirm a new session starts
normally, an existing session's interactions are unaffected, and the failure
is recorded somewhere the developer can find it without it appearing as a
user-facing error in the middle of normal work.

**Acceptance Scenarios**:

1. **Given** a `.continuity/` file is corrupted (invalid/unreadable content),
   **When** a session starts and Continuity attempts to load context,
   **Then** the session starts normally with the corrupted file's content
   omitted, and the corruption is logged locally rather than surfaced as a
   blocking error.
2. **Given** a background memory write fails partway (e.g., disk full,
   permission denied), **When** the failure occurs, **Then** the interactive
   session the developer is in is unaffected and no partially-written file is
   left in a state that breaks the next read.
3. **Given** `.continuity/` does not exist at all, **When** a session starts
   or a write trigger fires, **Then** Continuity treats this as the
   "no history yet" case (User Story 1, Scenario 3) or creates the directory
   as needed, without error.

---

### Edge Cases

- What happens when two Claude Code sessions on the same project (two
  terminals, or an interactive session plus a background/subagent session)
  each fire a memory-write trigger at close to the same time? → See
  [NEEDS CLARIFICATION] Q5 below; behavior is currently undefined.
- What happens when `.continuity/` content grows large over a long-lived
  project (months of decisions, tasks, learnings)? Does the bounded
  session-start subset stay bounded, and does anything ever prune or archive
  older entries? → See [NEEDS CLARIFICATION] Q2 and Q6.
- What happens when a `.continuity/` file was written or edited by someone
  other than the developer currently in the session (a teammate's commit, a
  merge, a shared branch) — is its content trusted the same as
  developer-authored content? → See [NEEDS CLARIFICATION] Q4.
- What happens when the project is not a git repository at all (no git
  present, or git present but the working tree is not a repo)? Continuity's
  triggers reference "meaningful git diffs"; the feature must not fail if git
  is unavailable — it should simply have one fewer trigger signal available.
- What happens when a memory write trigger fires but produces no meaningful
  new content (e.g., a git diff that only touches whitespace)? No file write
  should occur, and no failure should be logged for a legitimate no-op.
- What happens when the developer manually edits or deletes a `.continuity/`
  file mid-session? The next read should reflect the edited/deleted state
  without requiring a session restart, and should not treat the manual edit
  as a corruption.
- What happens when recorded context contains what looks like an instruction
  aimed at Claude (e.g., a "learning" entry someone wrote that reads like a
  command) rather than a fact about the project? → See
  [NEEDS CLARIFICATION] Q4.

## Requirements *(mandatory)*

### Functional Requirements

**Persistence**

- **FR-001**: The system MUST persist project-scoped context as
  human-readable Markdown/text files under a `.continuity/` directory at the
  project root — no database engine, embedded or otherwise, is installed or
  required to read or write this content.
- **FR-002**: The system MUST organize persisted context into distinct
  categories reflecting the intent's answered definition of "context":
  architectural/implementation decisions, stable project facts, current
  work state, active/unfinished tasks, known constraints, discoveries and
  learnings, established conventions, and session handoffs. Transient
  debugging detail, repeated explanations, and routine tool-call activity
  are explicitly excluded from what gets persisted.
- **FR-003**: The system MUST scope all persisted context to the individual
  project it was captured in; it MUST NOT mix context from one project into
  another project's `.continuity/` store.
- **FR-004**: Each persisted entry MUST retain enough provenance (at minimum,
  which category it belongs to and when it was captured) that a developer or
  a future session can tell where a piece of injected context came from,
  rather than presenting it as an unattributed assertion.

**Session-start context loading**

- **FR-005**: At the start of a new session, the system MUST load only a
  bounded, relevant subset of the persisted context — never the entirety of
  a prior conversation, and never the entirety of an unbounded
  `.continuity/` store regardless of how large it has grown.
- **FR-006**: Session-start context loading MUST NOT introduce latency that
  a developer performing normal work would notice, consistent with the
  "feels exactly as fast" bar; the exact bound and selection method are open
  ([NEEDS CLARIFICATION] Q2).
- **FR-007**: If no persisted context exists for a project (first-ever
  session, or a fresh clone with `.continuity/` absent or excluded), the
  system MUST start the session normally with no continuity context injected
  and no error shown.

**Memory writes**

- **FR-008**: The system MUST NOT run an LLM-based memory-summarization
  operation on every interaction; memory writes are triggered only by
  meaningful-change signals (e.g., significant file changes, meaningful git
  diffs, a task being completed or changed, a decision being made, a test
  milestone, or an explicit checkpoint).
- **FR-009**: `SessionEnd` MUST be one of the write triggers, but MUST NOT be
  the only one — a long-running or still-active session must be able to
  produce a checkpoint that a concurrent or later session can already see.
- **FR-010**: Memory writes MUST execute without blocking or delaying the
  interactive response the developer is waiting on; the concrete mechanism
  that achieves this without a separate server process is open
  ([NEEDS CLARIFICATION] Q3).
- **FR-011**: A memory write that produces no meaningful change to persist
  MUST be a silent no-op — it must not create empty or duplicate entries, and
  must not be logged as a failure.

**Failure handling**

- **FR-012**: Every Continuity read or write operation MUST fail open: on any
  error (missing directory, unreadable file, invalid/corrupted content,
  write failure, timeout), the system skips that operation, leaves Claude
  Code's normal behavior completely unaffected, and records the failure
  locally rather than surfacing it as a user-facing, session-blocking error.
- **FR-013**: A corrupted or invalid individual `.continuity/` file MUST be
  isolated to itself — it must not prevent loading context from the other,
  valid files in the same store.
- **FR-014**: The system MUST avoid leaving a `.continuity/` file in a
  partially-written state that would make it unreadable or misleading on the
  next read (e.g., via an atomic write or write-then-rename pattern).

**Distribution and footprint**

- **FR-015**: The system MUST ship strictly as a Claude Code plugin
  distributed via a GitHub-hosted marketplace; no other distribution
  mechanism is in scope.
- **FR-016**: The system MUST NOT require installing or using Go, any other
  standalone runtime, a database installation, a separate server process, or
  a cloud account/dependency for the base (MVP) implementation.
- **FR-017**: Uninstalling or disabling the plugin MUST leave Claude Code
  fully functional with no residual dependency on Continuity having ever run.

**Trust and safety of persisted content**

- **FR-018**: Content loaded from `.continuity/` and injected into a new
  session's context MUST be presented in a way that lets Claude and the
  developer distinguish "a fact/decision recorded by Continuity" from a
  live instruction in the current conversation, so that recorded content is
  not mistaken for a new directive to act on. The specific screening
  mechanism is open ([NEEDS CLARIFICATION] Q4.
- **FR-019**: The system's own operation MUST NOT require network access or
  send any project content to an external service as part of persisting or
  loading context (consistent with "no cloud dependency").
- **FR-020**: Because `.continuity/` is git-tracked by default (per the
  intent doc's answered question on storage, reaffirmed as Q1 below), the
  system MUST document, at install time and in-repo, that persisted content
  becomes part of shared git history, and MUST provide a documented,
  low-friction way for a developer to exclude `.continuity/` from version
  control on a given project (e.g., an add-to-`.gitignore` step). This does
  not by itself screen persisted content for secrets — see Concerns below.

### Key Entities

- **State Note**: The current understood state of the work on the project —
  what exists, what's in progress. Superseded by newer state notes rather
  than accumulated indefinitely.
- **Decision Record**: A specific architectural or implementation decision
  made during a session, with enough context to explain why, so it is not
  re-litigated in a later session.
- **Task Entry**: An active or recently-completed unit of work, with a status
  (active/blocked/done) distinct from a Decision Record.
- **Constraint**: A known limitation or hard requirement the project must
  respect, sourced from the intent doc or discovered during work.
- **Learning**: A discovery made during work (a gotcha, a non-obvious
  behavior, a convention established by trial) worth not re-discovering.
- **Session Handoff**: A short note written at a natural stopping point
  (not only `SessionEnd`) summarizing what a following session needs to know
  to continue.
- **Failure Log Entry**: A local record of a Continuity operation that failed
  open — what failed, when, and why — used for diagnosing degraded
  continuity without ever surfacing as a session-blocking error.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new session started on a project with prior Continuity
  history references at least one carried-over decision, fact, or unfinished
  task from that prior history without the developer re-explaining it, on
  every such session (verifiable by inspecting session-start context against
  the `.continuity/` store).
- **SC-002**: Across a sample of normal interactive turns, zero turns are
  measurably delayed by a Continuity memory write or an LLM-based memory
  operation — the developer cannot distinguish, by responsiveness alone,
  a turn that triggered a background memory write from one that did not.
- **SC-003**: A new session's injected context never contains the full text
  of a prior conversation — only the bounded, categorized subset described
  in FR-002/FR-005.
- **SC-004**: In 100% of tested failure conditions (missing directory,
  corrupted file, unreadable file, write failure), the session in progress
  continues to operate with no user-visible, session-blocking error.
- **SC-005**: Installing Continuity adds exactly one new dependency to a
  project's toolchain — the plugin itself — and zero new required processes,
  database engines, cloud accounts, or non-native runtimes.
- **SC-006**: A developer working a normal session cannot tell, from feel
  alone, whether Continuity is installed or not; a quantitative latency
  threshold is deferred until after the MVP is measured (per
  `docs/intent/continuity.md`, this is intentionally qualitative for v1).

## Assumptions

- Distribution target is a GitHub-hosted Claude Code plugin marketplace, per
  the intent doc's answered open question.
- Continuity is scoped per-project for the MVP; a separate cross-project,
  per-user memory layer is explicitly out of scope for this feature (per the
  intent doc's answered open question), though it may be a later addition.
- `.continuity/` uses a small set of purpose-named files (e.g., a state file,
  a decisions file, a tasks file, a learnings file) rather than one
  undifferentiated log, per the intent doc's answered open question on
  storage mechanism.
- "Meaningful-change" write triggers are heuristic (file changes, git diffs,
  task/decision events, test milestones, explicit checkpoints) rather than
  derived from a learned or configurable model, consistent with avoiding an
  expensive per-interaction LLM operation.
- No quantitative latency budget is set for v1; "feels exactly as fast" is
  judged qualitatively until real overhead is measured post-MVP, per the
  intent doc's answered open question.
- The plugin operates entirely on the local filesystem already available to
  Claude Code; it assumes standard file read/write permissions on the
  project directory and does not assume any particular OS-level sandboxing.
- Where `.continuity/` sits relative to version control (tracked vs.
  ignored) is not assumed here because it is a genuine open question with
  security implications — see [NEEDS CLARIFICATION] Q1.

## Concerns & Policy Tensions

These are not new scope questions; they are places where two already-answered
constraints pull against each other, or where an answer resolves the letter
of a question but leaves a residual risk. They are flagged rather than
silently resolved, per this stage's instruction to surface contradictions
instead of guessing past them.

- **Secrets can enter shared git history by default.** Q1 answers that
  `.continuity/` is git-tracked by default, with an opt-out available. FR-020
  operationalizes the opt-out, but neither the intent doc nor Q1's answer
  requires any content screening before a decision/learning/state entry is
  written. A session that records a credential, connection string, or
  client-confidential detail in `decisions.md` or `learnings.md` commits it
  to permanent shared history before any developer notices — the opt-out
  only helps a developer who already knows to use it. This directly conflicts
  with this toolkit's own secret-scanning-is-a-hard-gate posture for code
  changes (`CONVENTIONS.md` §review suite). Recommend the plan stage decide
  whether writes get a lightweight secret-pattern check before persisting, or
  whether the MVP accepts this risk and documents it prominently instead.
- **"No separate server process" vs. the Q3 async-write mechanism.**
  Q3 answers that memory writes use a "fire-and-forget" detached background
  process so the triggering hook returns immediately. A background process
  that outlives its triggering hook call is, by degree, the same shape as a
  small persistent server — the constraint and the answer do not draw a
  bright line between "a detached one-shot background task" (in scope) and
  "a standalone server process" (explicitly out of scope). FR-010 already
  flags the mechanism as open; this note makes the underlying contradiction
  explicit so the plan stage defines the boundary precisely (e.g., the
  process must exit after completing one write and must never bind a socket
  or listen for further events).
- **File locking (Q5) assumes a filesystem that supports advisory locks.**
  The "no separate server" constraint rules out a lock broker, so Q5's
  file-locking answer depends on the local filesystem honoring advisory
  locks reliably. This does not hold on all network or shared filesystems.
  Acceptable for a single-machine MVP; flag as a known gap rather than a
  silently assumed guarantee.
- **Unbounded durable growth vs. bounded, non-database selection.** Q6
  answers that durable files (`state.md`, `decisions.md`, `tasks.md`,
  `learnings.md`) are retained indefinitely, while FR-005/Q2 require the
  session-start subset to stay bounded without a database, embeddings, or
  vector store. A purely heuristic (e.g., recency-based) selection method
  will degrade in relevance quality as a project's durable history grows
  over months, with no stated point at which that degradation gets measured
  or addressed. Q2's own answer already anticipates re-measuring after the
  MVP ships; this note ties that follow-up explicitly to Q6's indefinite-
  retention choice.

## Open questions

- [x] [NEEDS CLARIFICATION: Q1 — Should `.continuity/` be committed to git
  (so context is shared across contributors and branches, matching the
  intent doc's "Git-friendly, portable" framing) or gitignored (local-only
  per developer machine)? These pull in different directions: committing it
  makes context shareable and durable across clones, but also means any
  sensitive fact, credential, or client detail a session ever wrote to
  `.continuity/decisions.md` or `.continuity/learnings.md` enters shared,
  permanent git history — the opposite of a secret-scanning/least-shared-
  data security posture. This cannot be resolved by a default; it needs an
  explicit decision (and, if tracked, a documented redaction discipline for
  what must never be written there).]
  Answer: I’d recommend yes, .continuity/ should be committed to Git by default. The main reason is that Continuity is project-level context, and committing it makes that context travel with the project: a new developer or a new machine can get the same decisions, current state, constraints, and learnings. However, we should design it so users can opt out later—for example, if a project contains sensitive or highly personal context. Recommended MVP decision: .continuity/ is Git-tracked by default. The plugin should provide an easy way to add it to .gitignore if the user wants local-only continuity.
- [x] [NEEDS CLARIFICATION: Q2 — What concrete bound (a line count, byte size,
  or token budget) defines the "bounded relevant subset" loaded at
  SessionStart, and what selection method picks which entries make that cut
  without a database, an embeddings/vector store, or a cloud call (all of
  which are out of scope)? Without an answer, "bounded" and "relevant" are
  both currently unverifiable requirements.]
  Answer: For the MVP, the injected context should have a soft target of ~100–200 lines (roughly 5–10 KB) per SessionStart, with the goal of keeping only the most relevant project state. This is a target, not a hard truncation limit—if the relevant context is smaller, load less; if it occasionally exceeds the target, Continuity can prioritize and compress it before injection.
- [x] [NEEDS CLARIFICATION: Q3 — What is the concrete non-blocking execution
  mechanism for asynchronous memory writes inside the Claude Code plugin/
  hook model, given that "no separate server process" is also a hard
  constraint? Plugin hooks typically run as short-lived processes tied to an
  event; achieving a write that "never blocks the interactive response"
  usually means detaching a background process from that hook, which is a
  different thing from a persistent server but needs to be named and agreed
  as in-scope, since the line between "a detached background process" and
  "a server" is exactly where this constraint could quietly be violated.]
  Answer: For the MVP, Continuity should use **fire-and-forget asynchronous background processing** for memory writes. The Claude Code hook should perform only the minimal work required to capture or queue the event, then return immediately. Any summarization, consolidation, or state update should happen in a separate background process after the hook returns, so the interactive Claude Code workflow is never waiting for memory processing. If the background process cannot be started or fails, Continuity logs the failure and Claude Code continues normally.
- [x] [NEEDS CLARIFICATION: Q4 — How should content loaded from `.continuity/`
  files be screened before it re-enters a session's context, given that
  those files are plain text a prior session (or a teammate, if Q1 resolves
  to "tracked") could have written to contain something that reads as an
  instruction rather than a fact (e.g., a "learning" entry phrased as a
  directive)? Treating all persisted content as unconditionally trustworthy
  context reintroduces the same class of risk as accepting instructions from
  any other untrusted external document.]
  Answer: For the MVP, content loaded from `.continuity/` should be treated as **trusted project context, not as instructions**. At `SessionStart`, Continuity should inject only a concise, relevant context block into Claude Code, clearly labeled as **Continuity context**. Claude should use it to understand project state, decisions, constraints, and work in progress, but it should not automatically execute commands or treat embedded text as higher-priority instructions. Any content that appears to contain instructions should be treated as project information unless the user explicitly asks Claude to act on it.
- [x] [NEEDS CLARIFICATION: Q5 — How are concurrent writes handled when two
  Claude Code sessions on the same project (two terminals, or an interactive
  session plus a background/subagent session) fire a memory-write trigger at
  close to the same time? Is last-write-wins acceptable, is there a lock,
  or does each session write to a distinct location that gets merged later?]
  Answer: For the MVP, concurrent writes should use **file locking with atomic writes**. Before updating shared `.continuity/` state, a session acquires a short-lived lock, reads the latest state, applies its update, writes the new version atomically, and releases the lock. This prevents two sessions from overwriting each other or leaving partially written files. If the lock is unavailable, the update should retry briefly and then fail gracefully rather than blocking Claude Code.
- [x] [NEEDS CLARIFICATION: Q6 — What is the retention/pruning policy for
  `.continuity/` content over the life of a long-running project? Without
  one, "bounded subset at session start" (FR-005) is at odds with an
  unbounded, ever-growing store, and a developer has no documented way to
  reset or prune it.]
  Answer: For the MVP, durable project context (state.md, decisions.md, tasks.md, learnings.md) should be retained indefinitely. Session-specific history under .continuity/sessions/ should follow a configurable retention period, defaulting to 60 days. Users can change the retention period based on their project needs. Important information promoted into durable context should not be removed during session-history pruning.
- [x] [NEEDS CLARIFICATION: Q7 — Does the plugin require any permission beyond
  reading and writing inside `.continuity/` — for example, running git
  commands to compute "meaningful git diffs," or reading files elsewhere in
  the project to detect "significant file changes"? A marketplace-
  distributed plugin's permission footprint is itself a trust/security
  question a reviewer or installer will ask, and it is not stated in the
  intent doc.]
  Answer: For the MVP, **Continuity should require no permissions beyond what Claude Code already grants to a plugin running within the project**. It needs access to read/write the project’s `.continuity/` directory and read the project information necessary to maintain context. It should not require access to external services, user-level files, cloud storage, or credentials. Any future capability that requires broader access should be explicitly opt-in rather than part of the default installation.
- [x] [NEEDS CLARIFICATION: Q8 — Where do "log the failure locally" entries
  (FR-012) live, how long are they kept, and must they be scrubbed of any
  content that caused the failure (e.g., a corrupted file's raw bytes),
  given the same sensitivity concerns raised in Q1?]
  Answer: Store failures in `.continuity/errors.log`; retain them for the configurable retention period (default **60 days**), and scrub logs so they contain only operational metadata—never raw file contents, conversation content, secrets, credentials, or other sensitive data.
- [x] [NEEDS CLARIFICATION: Q9 — Since the plugin can be updated independently
  of any given project's `.continuity/` content, what compatibility
  contract applies if a newer plugin version changes the file
  categories/format described in FR-002? Without one, an updated plugin
  reading an older project's files (or vice versa, a teammate on an older
  plugin version reading a newer project's files) has undefined behavior.
  (Note: an earlier draft of this answer duplicated Q8's answer text
  verbatim and did not actually address versioning/compatibility; that
  copy-paste error has been reverted and this question is genuinely still
  open — it needs its own answer, not Q8's.)]
  Answer: **Continuity should use an explicit schema version in `.continuity/metadata.json`, with backward compatibility for at least the current and previous schema versions; newer plugin versions should migrate older state forward when safe, while older plugins should detect unsupported newer versions and fail open without modifying the files.**
- [x] [NEEDS CLARIFICATION: Q10 — Is the scope a single project root only, or
  must Continuity also define behavior for monorepos or multiple git
  worktrees, where "the project" and therefore the correct `.continuity/`
  location may be ambiguous?]
  Answer: **MVP scope is a single project root only:** Continuity operates on the project root where it is installed and stores all project context under that project’s `.continuity/` directory; multi-project/global context is out of scope for the MVP.
