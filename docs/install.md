# Install notes: `.continuity/` and git

## Install per coding agent

Continuity is one plugin with one manifest per coding agent. Install it from this
repository's marketplace in whichever agent you use:

### Claude Code

```text
/plugin marketplace add navjyotnishant/continuity
/plugin install continuity@continuity
```

Start a new session afterwards.

### Codex

Add the marketplace `https://github.com/navjyotnishant/continuity.git` in Codex's plugin
settings (CLI: `codex plugin marketplace add <owner/repo|git-url|path>`, then
`codex plugin add continuity@<marketplace-name>`), then install `continuity`. Codex asks
you to **review and trust the plugin's hooks** once. Until you do, it installs but never
recalls or captures. Codex loads skills, not commands, so checkpoint with the
`continuity-checkpoint` skill.

### Cursor

Add the same repository as a team or local marketplace (CLI: `cursor-agent plugin
marketplace add <git-url>`). Cursor has no headless plugin-install command: after the
marketplace is added, install `continuity` from Cursor's plugin UI. Cursor reads
`.cursor-plugin/plugin.json` and its hooks from `hooks/cursor-hooks.json`.

### Claude Desktop (Cowork): not supported

Cowork does not run plugin hooks, so Continuity can neither recall nor capture there
([anthropics/claude-code#40495](https://github.com/anthropics/claude-code/issues/40495)).
This section changes once that is fixed.

### Updating

Refresh the marketplace, reinstall, and start a new session. A running session keeps
the version it started with.

## `.continuity/` is git-tracked by default

Continuity writes its state, decisions, tasks, and learnings into a
`.continuity/` directory at the root of your project. By default this
directory is **not** ignored — it is ordinary, trackable content in your
repo, and a `git add`/`git commit` will pick it up like any other file
(Q1). That is deliberate: the point of Continuity is for a teammate's
session to inherit the same context yours did, which only works if that
context travels with the repo.

The consequence: anything Continuity persists becomes part of your shared
git history, on every clone, forever (or until history is rewritten). If
your project's decisions/tasks notes could ever contain something you
would not want in shared history — internal URLs, customer specifics, a
credential pasted into a chat — treat `.continuity/` the same way you'd
treat any other tracked file with that risk, and opt out per below.

## Secret scanning is a mitigation, not a guarantee

Continuity runs `plugins/continuity/lib/secret_scan.py` over content before it writes it, to
catch common credential patterns (API keys, tokens, etc.). This reduces
risk but **does not eliminate it**: a scan can always have a false negative
— a secret in a shape the patterns don't recognize ships into git history
exactly as if the scan weren't there.

Do not treat the scan as a substitute for your own judgment about what you let Continuity persist.

If you're unsure, opt out of git-tracking (below) or keep sensitive detail
out of the conversation entirely.

## Opting `.continuity/` out of version control

This is purely a version-control decision — Continuity keeps reading and
writing `.continuity/` on disk exactly as before either way. Only whether
git tracks it changes (FR-020).

1. Add an ignore rule:

   ```sh
   echo '.continuity/' >> .gitignore
   ```

2. If `.continuity/` has already been committed in this repo, untrack the
   existing copy (this leaves the files on disk, it only removes them from
   git's index going forward):

   ```sh
   git rm -r --cached .continuity/
   git commit -m "Stop tracking .continuity/"
   ```

3. Confirm the outcome:

   ```sh
   git status
   ```

   `.continuity/` (and files under it) should no longer appear as tracked
   or as something `git add` would pick up, while Continuity continues to
   read and write it normally in the current and future sessions.

## Configuring retention and tracking in `metadata.json`

`.continuity/metadata.json` holds two fields you can hand-edit at any
time; `plugins/continuity/lib/write_memory.py` and `plugins/continuity/lib/retention.py` re-read this file on every run,
so an edit takes effect immediately, without restarting a session:

- `retention_days` (default `60`) — how long session-history files under
  `.continuity/sessions/` and `.continuity/errors.log` are kept before
  being pruned. Durable files (`state.md`, `decisions.md`, `tasks.md`,
  `learnings.md`) are never pruned by this setting; only promoted content
  in those files sticks around past the window.
- `git_tracked` (default `true`) — a record of whether this project's
  `.continuity/` is intended to be under version control. This field is
  informational for Continuity's own bookkeeping; it does not itself add
  or remove `.gitignore` entries or run `git rm --cached` for you — use
  the opt-out steps above to actually change git's behavior, and update
  this field to match afterwards.
