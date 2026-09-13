# Install notes: `.continuity/` and git

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

Continuity runs `lib/secret_scan.sh` over content before it writes it, to
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
time; `write_memory.sh` and `retention.sh` re-read this file on every run,
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
