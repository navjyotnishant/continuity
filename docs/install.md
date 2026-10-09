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

Add the marketplace and install the plugin:

```sh
codex plugin marketplace add navjyotnishant/continuity
codex plugin add continuity@continuity
```

Add the marketplace **without** an `@<branch>` suffix. A marketplace added as
`navjyotnishant/continuity@some-branch` stays pinned to that branch, so later updates
reinstall whatever that branch holds instead of the latest release. Codex asks
you to **review and trust the plugin's hooks** once. Until you do, it installs but never
recalls or captures. Codex loads skills, not commands, so checkpoint with the
`continuity-checkpoint` skill.

Codex support is **beta**: it is built and unit-tested, but not yet verified
in a live Codex session. This will be confirmed in a later patch release.

### Cursor

Add the same repository as a marketplace, then install `continuity` from Cursor's
plugin settings. Cursor has no command-line install:

```sh
cursor-agent plugin marketplace add https://github.com/navjyotnishant/continuity
```
 Cursor reads
`.cursor-plugin/plugin.json` and its hooks from `hooks/cursor-hooks.json`.

### Claude Desktop (Cowork): limited to the Cowork workspace

Install through the desktop app (Customize → Plugins); a copy installed only from the
CLI is not visible to Cowork. Continuity's hooks run in Cowork, but in a cloud
container whose working directory is `/home/claude`, so:

- the store is created at `/home/claude/.continuity/`, not in the folder you connected;
- the container is reset between sessions, so the next session starts with an empty
  store and recalls nothing.

Notes therefore last only for the current session (tested 2026-10-08). Local Cowork
and the desktop app's Code tab are untested.

### Updating

Refresh the marketplace, update the plugin, then start a new session. A running session
keeps the version it started with.

| Agent | Update | Check the installed version |
|---|---|---|
| Claude Code | `/plugin marketplace update continuity`, then update `continuity` in `/plugin` (CLI: `claude plugin marketplace update continuity` and `claude plugin update continuity@continuity`) | `claude plugin list` |
| Codex | `codex plugin marketplace upgrade continuity`, then `codex plugin add continuity@continuity` | `codex plugin list --json` (the `installed` entry's `version`) |
| Cursor | `cursor-agent plugin marketplace update continuity`, then update `continuity` in Cursor's plugin settings | the plugin's version in Cursor's plugin settings |

**If an update installs an old version**, the marketplace is pinned to a branch rather
than the default one. This happens with a marketplace added with an `@<branch>` suffix,
or one pointing at a branch that has since been deleted. Remove it and add it again
without a branch, then update the plugin:

```sh
# Codex
codex plugin marketplace remove continuity
codex plugin marketplace add navjyotnishant/continuity
codex plugin add continuity@continuity

# Cursor (then update continuity in Cursor's plugin settings)
cursor-agent plugin marketplace remove continuity
cursor-agent plugin marketplace add https://github.com/navjyotnishant/continuity
```

Codex may ask you to trust the plugin's hooks again after a reinstall, or after an
update that adds a hook (such as the end-of-turn `Stop` hook).

## `.continuity/` is git-tracked by default

Continuity writes its state, decisions, tasks, and learnings into a
`.continuity/` directory at the root of your project. By default this
directory is **not** ignored — it is ordinary, trackable content in your
repo, and a `git add`/`git commit` will pick it up like any other file
(Q1). That is deliberate: the point of Continuity is for a teammate's
session to inherit the same context yours did, which only works if that
context travels with the repo.

Only Continuity's local, transient files are kept out of git, by a
`.continuity/.gitignore` it writes for you: the raw notes waiting to be saved
(`.staged/`, not yet secret-scanned), the per-turn marker (`.turn-edited`), the
lock, `errors.log`, and temp files. Everything else, including `state.md`,
`tasks.md`, `decisions.md`, `learnings.md`, `sessions/` and `metadata.json`, is
committed with your repo. An existing file is never overwritten, so your team
can edit it.

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
