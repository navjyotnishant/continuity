# Verification: V1–V5 live spike (CONTINUI-56)

Ran 2026-09-27 against `claude` 2.1.278, `codex` (codex-cli) 0.141.0, `cursor-agent`
2026.09.26-dd393fe (self-updated mid-session from the 2026.08.11 build reported at
task start). All work done in a scratch directory outside the repo; a throwaway
recorder plugin (`record.py` + `hooks/hooks.json` + `hooks/cursor-hooks.json` +
per-agent manifests, exactly as specified in Task 1 Step 1 / Task 4 Step 3) was
installed into each agent for the duration of the spike and fully uninstalled
afterward (see "Cleanup" below). Nothing under `~/.codex` or `~/.cursor` other than
the recorder install/marketplace entries and one marketplace ref-refresh was
touched.

## Results table

| # | Check | Result |
|---|---|---|
| V1 | Cursor does not also load `hooks/hooks.json`; every Cursor payload carries camelCase `hook_event_name` | **PASS.** 4/4 recorded Cursor payloads (`sessionStart`, `afterFileEdit`, `afterShellExecution`, `sessionEnd`) carry `hook_event_name` in camelCase and only camelCase. No PascalCase event name appeared in any Cursor recording, so Cursor's manifest-named `cursor-hooks.json` was the only hook config it loaded — `hooks/hooks.json` in the same plugin directory was not also picked up. `detect_agent` needs no rewrite: `CURSOR_VERSION` is present on every Cursor payload's env, and `hook_event_name` is camelCase on every one, so either signal works as documented in design.md. |
| V2 | Exact Codex 0.141 `apply_patch` header lines, `PostToolUse` payload shape, env vars | **NOT OBTAINED LIVE — confirmed by static inspection instead.** No live Codex hook payload could be recorded (see "Codex blocker" below). Static inspection of the installed `codex` binary's embedded tool-use system prompt (`strings` on `/Users/navjyotnishant/.local/bin/codex`) confirms the exact header lines design.md assumes: `*** Add File: <path>`, `*** Delete File: <path>`, `*** Update File: <path>`, and `*** Move to: <path>` (rename form), inside a `*** Begin Patch` / `*** End Patch` envelope. This matches `patch_paths`'s expected header set exactly. The live `PostToolUse` payload shape (whether `tool_input.command` is a string or list) and the Codex-specific env vars (`PLUGIN_ROOT` vs `CLAUDE_PLUGIN_ROOT` alias) could **not** be confirmed live. |
| V3 | Codex and Cursor accept a marketplace plugin with `source: "./"` (repo root) | **SPLIT RESULT — Codex fails silently, Cursor passes.** See "V3 detail" below. Per the task rule ("if either refuses a root-level source, STOP and report BLOCKED"), this is reported as **BLOCKED for Codex** rather than worked around; the repo was not restructured. |
| V4 | A Codex skill's shell can use `${CLAUDE_PLUGIN_ROOT}` | **NOT OBTAINED.** Requires a working live Codex session (blocked, see below). |
| V5 | `codex exec` and `cursor-agent -p` run plugin hooks headless | **Cursor: PASS.** `cursor-agent -p --plugin-dir <dir> --force` ran all four Cursor hook events headless with no interactive prompt. **Codex: NOT OBTAINED** — `codex exec` never got past model selection to reach a point where hooks could run (see below); hook-trust behavior itself was never exercised. |

## V3 detail: marketplace `source: "./"` (repo root)

Tested with a from-scratch local marketplace whose `.claude-plugin/marketplace.json`
plugin entry is `"source": "./"` (root), directly mirroring what
`.claude-plugin/marketplace.json` in this repo already does for Claude Code.

- **Cursor**: `cursor-agent plugin marketplace add <git-url> --git-ref spike/recorder`
  (a throwaway branch pushed to `origin` for this check only, deleted afterward —
  see "Scratch branch" below) reported `Added marketplace continuity (1 plugin)` and
  correctly showed the `continuity` plugin with its real description. Root-sourced
  marketplace entries work in Cursor.
- **Codex**: `codex plugin marketplace add <local-path>` (root-sourced
  `.claude-plugin/marketplace.json`) succeeds with no error and the marketplace is
  listed by `codex plugin marketplace list`, but `codex plugin list --marketplace
  <name> --available --json` returns `{"installed": [], "available": []}` — the
  plugin entry is **silently dropped**, no error at any step. Isolated the cause by
  building an otherwise-identical marketplace whose plugin entry uses
  `"source": "./plugin-a"` (one level under root, exactly like the working
  `njagents` marketplace's `"source": "./operations/bug-triage-agent"` in the user's
  own `~/.codex/.tmp/marketplaces/njagents/.claude-plugin/marketplace.json`): that
  one indexed correctly and showed up in `--available`. **Root-level `source: "./"`
  is the specific thing Codex drops.** Per the task's explicit rule, this is reported
  as BLOCKED rather than restructuring the repo. Whether Task 4's design (single
  repo root marketplace, `source: "./"` for the `continuity` entry that all three
  agents currently share via `.claude-plugin/marketplace.json`) needs a fallback
  subfolder layout for Codex specifically is a decision for the controller, not made
  here.

## Codex blocker (why V2, V4, V5-Codex are NOT OBTAINED)

Hook-trust bypass: the brief's documented non-interactive path,
`codex exec --dangerously-bypass-hook-trust`, exists (confirmed via `codex exec
--help`) but this session's own sandbox denies the command by name pattern before it
reaches Codex at all ("Permission for this action was denied by the Claude Code auto
mode classifier. Reason: [Safety Bypass Flag]"). No `-c key=value` config override
for hook trust was found in `codex --help`, `codex plugin --help`, or `codex features
list`; `plugin_hooks` is a `removed` feature flag (hooks are unconditionally
`stable`), so there's no feature toggle either. The only persisted trust state found
was per-project **workspace** trust (`[projects."<path>"].trust_level = "trusted"` in
`~/.codex/config.toml`), which is a different, broader mechanism than hook trust and
was left untouched per the task's instruction not to hand-edit trust state files.

Independently of hook trust, every attempted `codex exec` call in this environment —
with or without the bypass flag, with the recorder installed or not — failed before
reaching a tool call: the account's configured model (`gpt-5.6-terra`, this
machine's default in `~/.codex/config.toml`) is rejected by the server with
`"The 'gpt-5.6-terra' model requires a newer version of Codex. Please upgrade to the
latest app or CLI and try again."` Every other model name tried (`gpt-5.3-codex-low`,
`gpt-5.1`, `gpt-5-mini`, `o4-mini`, `gpt-5.6-terra-low`, `gpt-5.6-terra-none`,
`codex-mini-latest`, `gpt-5-codex`, `auto`, `gpt-4o`, `gpt-4.1`, `o3`) was rejected
with `"... is not supported when using Codex with a ChatGPT account."` The only
other locally installed `codex` binary (`/opt/homebrew/bin/codex`, 0.139.0) is
*older*, not newer, so there is no available upgrade path within scope (running
`codex update` would change the user's global Codex install, which is outside what
this task approved). This is an environment/account limitation, not a
Continuity/plugin-hook problem — but it means **no live Codex hook payload of any
kind could be recorded**, so `PostToolUse-apply_patch.json`, `PostToolUse-Bash.json`
(Codex variant), Codex `SessionStart`, and Codex `SessionEnd` fixtures do not exist.

**Reporting this as NEEDS_CONTEXT for the Codex portion of V2/V4/V5**, per the task's
"When You're in Over Your Head" instruction, rather than fabricating payloads or
editing trust/model config to force a call through.

## Fix round 1: `_env` contamination in three Cursor fixtures

A reviewer flagged that `cursor/afterFileEdit.json`, `cursor/afterShellExecution.json`
and `cursor/sessionEnd.json` recorded `_env.CLAUDE_PLUGIN_ROOT` /
`_env.CURSOR_PLUGIN_ROOT` as `/Users/navjyotnishant/.claude/plugins/cache/claude-plugins-official/superpowers/6.4.1`
— an unrelated plugin's cache path, not something Cursor itself sets for the
recorder. `cursor/sessionStart.json` (recorded first in the same run) correctly
showed the recorder's own path, so the other three picked up contamination
partway through that run.

**Root cause found**: there is a long-lived `cursor-agent worker` background
daemon on this machine (`ps -ef | grep cursor-agent` shows a `worker start`
process under `~/.cursor/plugins/cache/njagents/bug-triage-agent/...`, running
since before this session). `cursor-agent -p` dispatches hook execution through
this pre-existing worker rather than a fresh child process, so the worker's own
captured environment (frozen at whatever it was when the worker started) leaks
into hook invocations partway through a session — not the environment of the
`cursor-agent -p` command itself.

**Attempted a clean re-record** (one more `cursor-agent -p` run, in a fresh scratch
repo, per the reviewer's suggested command):

```
env -u CLAUDE_PLUGIN_ROOT -u CURSOR_PLUGIN_ROOT -u CLAUDE_PROJECT_DIR \
  RECORD_DIR=<fresh dir> \
  cursor-agent -p "Edit notes/a.txt to say hello world, then run git status" \
  --plugin-dir <recorder> --force --output-format text
```

This did **not** clear the contamination — `afterFileEdit`, `afterShellExecution`
and `sessionEnd` still showed the same stray `superpowers/6.4.1` path, confirming
the cause is the persistent worker daemon's frozen environment, not the launching
shell's environment (which `env -u` controls but the worker never inherits from,
since it was already running). A clean run is not achievable from within this
harness without stopping/restarting a daemon that isn't this task's to manage.

**Resolution applied (fallback, as instructed)**: deleted the two contaminated
keys (`CLAUDE_PLUGIN_ROOT`, `CURSOR_PLUGIN_ROOT`) from `_env` in all three affected
fixtures. `CURSOR_PROJECT_DIR`, `CURSOR_VERSION` and `CLAUDE_PROJECT_DIR` — all
correctly set on every event including these three — were kept. `sessionStart.json`
was not touched; its `_env` already correctly showed the recorder's own path and
was never contaminated.

## Fixtures written

All 8 non-Codex event fixtures named in Step 7 exist, scrubbed and verified
(`{"payload": {...}, "_env": {...}}` shape):

- `tests/fixtures/agents/claude/SessionStart.json`
- `tests/fixtures/agents/claude/PostToolUse-Edit.json`
- `tests/fixtures/agents/claude/PostToolUse-Bash.json`
- `tests/fixtures/agents/claude/SessionEnd.json`
- `tests/fixtures/agents/cursor/sessionStart.json`
- `tests/fixtures/agents/cursor/afterFileEdit.json`
- `tests/fixtures/agents/cursor/afterShellExecution.json`
- `tests/fixtures/agents/cursor/sessionEnd.json`

**Not written (Codex blocked, see above):**

- `tests/fixtures/agents/codex/SessionStart.json`
- `tests/fixtures/agents/codex/PostToolUse-apply_patch.json`
- `tests/fixtures/agents/codex/PostToolUse-Bash.json`
- `tests/fixtures/agents/codex/SessionEnd.json`

Task 2's unit tests for the Codex path will need to be either (a) skipped/marked
pending until a working Codex live session can record real fixtures, or (b)
hand-built from the static `apply_patch` header confirmation above plus design.md's
existing assumptions, clearly labeled as unverified-live. That decision belongs to
whoever picks up Task 2; this task does not fabricate Codex fixtures to unblock it.

## Recorder plugin (Step 1)

Built at `$S/recorder` (scratch, never committed) with:

- `record.py` — exactly the script in the brief.
- `hooks/hooks.json` — Claude Code + Codex schema, `SessionStart` / `PostToolUse`
  (matcher `Edit|Write|MultiEdit|Bash`) / `SessionEnd`, all calling
  `python3 "${CLAUDE_PLUGIN_ROOT}/record.py"`.
- `hooks/cursor-hooks.json` — Cursor schema, `sessionStart` / `afterFileEdit` /
  `afterShellExecution` / `sessionEnd`, all calling
  `python3 "${CURSOR_PLUGIN_ROOT}/record.py"`.
- `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json` — copied from Task 4
  Step 3's exact content (recorder's own copies only, per this task's brief; Task 4
  creates the real ones in the repo).
- `.claude-plugin/plugin.json` — copy of the repo's existing plugin.json.
- `.claude-plugin/marketplace.json` — scratch-only marketplace manifest needed to
  register the recorder as a local Codex marketplace (not part of the brief's fixed
  file list; required because `codex plugin marketplace add` needs a marketplace
  manifest, not a bare plugin directory).
- `skills/continuity-checkpoint/SKILL.md` — stub, not exercised.

## Step 2: install-path commands found

- **Claude Code**: `claude -p --plugin-dir <path>` loads a local plugin directory
  directly, no marketplace or install step needed for a spike.
- **Codex**:
  - `codex plugin marketplace add <local-path|git-url|owner/repo>` — registers a
    marketplace. Local paths work (see V3 for the root-vs-subfolder caveat).
  - `codex plugin add <plugin>@<marketplace>` — installs a plugin from a registered
    marketplace by name.
  - `codex plugin list [--marketplace NAME] [--available] [--json]` — lists
    installed/available plugins.
  - `codex plugin remove <plugin>@<marketplace>` / `codex plugin marketplace remove
    <name>` — uninstall.
  - No `--plugin-dir`-style direct-load flag exists for Codex; a marketplace is
    always required.
- **Cursor**:
  - `cursor-agent --plugin-dir <path>` — loads a local plugin directory directly for
    a single invocation (used for all Cursor recordings in this spike; no
    marketplace or install step needed).
  - `cursor-agent plugin marketplace add <git-url> [--git-ref REF]` — registers a
    marketplace; **git URL only, no local-path form** (confirmed via `cursor-agent
    plugin marketplace add --help`).
  - `cursor-agent plugin marketplace list` / `remove <nameOrUrl>` / `update
    <nameOrUrl>` — manage marketplaces.
  - No headless `cursor-agent plugin install`-style command exists; the CLI's own
    help says "use /plugins in interactive mode to install plugins from this
    marketplace." This spike used `--plugin-dir` instead, which is sufficient for
    V1/V4/V5 hook-payload recording and does not require marketplace install at all.

## Scratch branch (Cursor V3 git-URL requirement)

Cursor's marketplace only accepts a git URL, so the real `.codex-plugin/plugin.json`,
`.cursor-plugin/plugin.json`, `hooks/cursor-hooks.json`, and a stub
`skills/continuity-checkpoint/SKILL.md` (all content matching Task 4 Step 3, used
here only to give the marketplace something real to index — **not the recorder**,
which was tested separately via `--plugin-dir`) were committed to a throwaway branch
`spike/recorder`, pushed to `origin` for the marketplace-add call, then deleted from
both origin and local once the check was done:

```
git checkout -b spike/recorder
# add .codex-plugin/plugin.json, .cursor-plugin/plugin.json, hooks/cursor-hooks.json,
# skills/continuity-checkpoint/SKILL.md (Task 4 Step 3 content)
git commit -m "spike: throwaway manifests for V3 marketplace-install check (not for merge)"
git push -u origin spike/recorder
cursor-agent plugin marketplace add https://github.com/navjyotnishant/continuity --git-ref spike/recorder
# ... V3 check ...
git push origin --delete spike/recorder
git checkout feat/multi-agent
git branch -D spike/recorder
```

This branch was never merged, no `feat/multi-agent` or `develop`/`main` commit
references it, and it no longer exists on origin.

## Cleanup

**Codex** — added and then fully removed:

- Marketplace `continuity-recorder-mkt` (local, root-sourced — this is the one that
  demonstrated the V3 silent-drop) — removed via `codex plugin marketplace remove`.
- Marketplace `subfolder-test-mkt` (local, subfolder-sourced, used to install the
  recorder for the one working Codex install path) — plugin removed via `codex
  plugin remove`, then marketplace removed via `codex plugin marketplace remove`.
- Confirmed via `codex plugin marketplace list` afterward: back to exactly the four
  pre-existing marketplaces (`openai-primary-runtime`, `openai-bundled`, `njagents`,
  `openai-curated`). Nothing else under `~/.codex` was touched; no trust files were
  edited.

**Cursor** — added and then restored:

- The user already had a `continuity` marketplace registered (pointing at this
  repo's default branch) from before this session. This spike temporarily repointed
  it at the throwaway `spike/recorder` branch via `cursor-agent plugin marketplace
  add ... --git-ref spike/recorder` (same marketplace name/URL, so this updates its
  indexed ref rather than adding a new entry) to run the V3 check, then ran
  `cursor-agent plugin marketplace update continuity` (no `--git-ref`, i.e. back to
  the default branch) before deleting the remote `spike/recorder` branch. Confirmed
  afterward with another `marketplace update continuity` (succeeds, 1 plugin
  indexed) that it resolves cleanly now that the branch is gone.
- No plugin was ever installed from the `continuity` marketplace in this session
  (Cursor has no headless plugin-install path; recording used `--plugin-dir`
  instead), so there is nothing installed to remove.
- A pre-existing `~/.cursor/plugins/cache/continuity/...` cache directory was found
  and left untouched — it predates this session (it has no `spike/recorder`-only
  files in it) and is not something this task's recorder work touched.
- `cursor-agent` self-updated its version between the first (2026.08.11) and second
  (2026.09.26) invocation in this session; this is the CLI's own auto-update
  behavior, not an action taken by this task.

## Scrub and gitleaks evidence

Re-run after Fix round 1 (the `_env` contamination fix above); this is the current,
authoritative evidence for the committed fixtures:

```
$ grep -ril "navjyot" tests/fixtures/agents
NONE FOUND

$ grep -rl "@" tests/fixtures/agents
tests/fixtures/agents/cursor/sessionStart.json
tests/fixtures/agents/cursor/sessionEnd.json
tests/fixtures/agents/cursor/afterShellExecution.json
tests/fixtures/agents/cursor/afterFileEdit.json
# each hit is only the scrubbed placeholder "user@example.com", not a real address —
# confirmed individually by extracting the matched string from each file.

$ grep -roE '[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}' tests/fixtures/agents
NONE FOUND

$ gitleaks detect --no-git --source tests/fixtures/agents
5:01PM INF scanned ~7173 bytes (7.17 KB) in 19.1ms
5:01PM INF no leaks found
```

## Differences from plan Task 2

None found that require a Task 2 code change. Specifically checked and confirmed
matching design.md's assumptions:

- Cursor: `hook_event_name` is camelCase on every payload (confirmed live, 4/4
  events) — `detect_agent`'s reliance on this (or on `CURSOR_VERSION`, also present
  on every payload) needs no rewrite.
- Claude Code: `PostToolUse` for `Edit` carries `tool_input.file_path`,
  `tool_input.old_string`/`new_string`; for `Bash` carries `tool_input.command` as a
  plain string. `SessionStart`/`SessionEnd` shapes match design.md's mapping.
  Confirmed live, byte-shape matches what `agents.py` (per design.md) expects.
- Codex `apply_patch` header lines (`*** Add File:`, `*** Delete File:`,
  `*** Update File:`, `*** Move to:`) confirmed via static inspection of the
  installed binary's embedded tool documentation — matches `patch_paths`'s assumed
  header set exactly. **Not** confirmed live (see Codex blocker above), so this is
  a lower-confidence confirmation than the live-recorded Claude/Cursor shapes.

**One new finding not in design.md's capability table**: design.md's V3 row says
only "Stop and bring back to the user" as the fallback with no detail on *which*
agent might fail it or how. This spike found the failure is **Codex-specific and
silent** (no error, empty `--available` listing) rather than an explicit rejection,
and that the specific trigger is a **root-level** `source: "./"` — a subfolder
source works fine in Codex. Cursor accepts root-level sources without issue. This
narrows the fallback question design.md left open: if the controller decides to
work around this rather than accept the BLOCKED status, the fix is a Codex-only (or
universal) subfolder-sourced marketplace entry, not a full repo restructure.
