"""tests/test_write_memory_basic.py — the write path (T014).

Drives the Content Channel end to end: a staged note under
`.continuity/.staged/` is consolidated into its durable file, a handoff file
appears under `.continuity/sessions/`, and the staged note is consumed. Also
drives hooks/capture-trigger.py the way Claude Code does — a PostToolUse JSON
payload on stdin — to prove a whitespace-only edit writes nothing at all
(FR-011) while a real edit reaches the writer.

Carries T021 as well: a static check that neither `lib/write_memory.py` nor
`hooks/session-start.py` can reach the network or shell out to anything but
python/git, which is what makes "no turn pays for an LLM call" a property of
the code rather than a claim about it.
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)

from lib.select_context import _entries
from lib.write_memory import staged_dir, write_memory

CAPTURE_TRIGGER_HOOK = os.path.join(REPO_ROOT, "hooks", "capture-trigger.py")


def stage(project_root, kind, body, suffix="20260912T140501Z-4242"):
    """Write one staged note, exactly as Claude's Write tool would (T017a)."""
    path = os.path.join(
        project_root, ".continuity", ".staged", "{}-{}.md".format(kind, suffix)
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(body)
    return path


def sessions_files(project_root):
    sessions = os.path.join(project_root, ".continuity", "sessions")
    try:
        return sorted(name for name in os.listdir(sessions) if name.endswith(".md"))
    except OSError:
        return []


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class TestWriteMemory(unittest.TestCase):
    def test_staged_decision_becomes_a_durable_entry_and_a_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = stage(
                tmp,
                "decision",
                "# Store memory as plain Markdown\n\n"
                "Chosen over SQLite so the store stays diffable and reviewable.\n",
            )

            handoff_path = write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            entries = _entries(store, "decisions.md")
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["heading"], "Decision: Store memory as plain Markdown")
            self.assertEqual(entries[0]["fields"]["category"], "decision")
            self.assertTrue(entries[0]["fields"]["captured_at"].endswith("Z"))
            self.assertIn("diffable", "\n".join(entries[0]["body"]))

            self.assertFalse(os.path.exists(staged), "staged note must be consumed")
            self.assertEqual(len(sessions_files(tmp)), 1)
            self.assertIsNotNone(handoff_path)
            self.assertIn("trigger: file-change", read(handoff_path))
            self.assertFalse(os.path.exists(os.path.join(store, ".lock")))

    def test_task_note_gets_a_status_and_a_handoff_note_becomes_the_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "task", "Wire the PostToolUse trigger\n\nBlocked on detachment.\n")
            stage(
                tmp,
                "handoff",
                "Read path is done; the writer is next.\n",
                suffix="20260912T140502Z-4242",
            )

            handoff_path = write_memory(tmp, "explicit-checkpoint")

            entries = _entries(os.path.join(tmp, ".continuity"), "tasks.md", require_status=True)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["fields"]["status"], "active")
            self.assertIn("Read path is done", read(handoff_path))

    def test_staged_learning_becomes_a_durable_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = stage(
                tmp,
                "learning",
                "# os.replace() is atomic on Windows too\n\n"
                "Confirmed via the stdlib docs; same filesystem only.\n",
            )

            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            entries = _entries(store, "learnings.md")
            self.assertEqual(len(entries), 1)
            self.assertEqual(
                entries[0]["heading"], "Learning: os.replace() is atomic on Windows too"
            )
            self.assertEqual(entries[0]["fields"]["category"], "learning")
            self.assertTrue(entries[0]["fields"]["captured_at"].endswith("Z"))
            self.assertIn("same filesystem only", "\n".join(entries[0]["body"]))
            self.assertFalse(os.path.exists(staged), "staged note must be consumed")

    def test_appending_keeps_earlier_entries_parseable(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "learning", "# First\n\nOne.\n")
            write_memory(tmp, "file-change")
            stage(tmp, "learning", "# Second\n\nTwo.\n", suffix="20260912T140503Z-4242")
            write_memory(tmp, "file-change")

            entries = _entries(os.path.join(tmp, ".continuity"), "learnings.md")
            self.assertEqual(
                [entry["heading"] for entry in entries],
                ["Learning: First", "Learning: Second"],
            )

    def test_body_heading_cannot_forge_a_new_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Real entry\n\n## Not a second entry\n\nBody.\n")
            write_memory(tmp, "file-change")

            entries = _entries(os.path.join(tmp, ".continuity"), "decisions.md")
            self.assertEqual([entry["heading"] for entry in entries], ["Decision: Real entry"])

    def test_nothing_staged_writes_nothing_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = os.path.join(tmp, ".continuity")
            os.makedirs(staged_dir(store))

            self.assertIsNone(write_memory(tmp, "session-end"))

            self.assertEqual(sessions_files(tmp), [])
            self.assertEqual(sorted(os.listdir(store)), [".staged"])

    def test_secret_line_is_dropped_and_logged_without_losing_the_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(
                tmp,
                "decision",
                "# Deploy credentials live in the environment\n\n"
                "The CI role is assumed at runtime.\n"
                "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n"
                "Nothing else is stored locally.\n",
            )

            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            decisions = read(os.path.join(store, "decisions.md"))
            self.assertIn("assumed at runtime", decisions)
            self.assertIn("Nothing else is stored locally", decisions)
            self.assertNotIn("AKIAIOSFODNN7EXAMPLE", decisions)

            errors = read(os.path.join(store, "errors.log"))
            self.assertIn("secret-blocked", errors)
            self.assertIn("aws-key-pattern", errors)
            self.assertNotIn("AKIAIOSFODNN7EXAMPLE", errors)

    def test_unknown_staged_kind_is_dropped_and_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Kept\n\nBody.\n")
            orphan = stage(tmp, "gibberish", "Unroutable.\n", suffix="20260912T140504Z-1")

            write_memory(tmp, "file-change")

            store = os.path.join(tmp, ".continuity")
            self.assertFalse(os.path.exists(orphan))
            self.assertIn("Kept", read(os.path.join(store, "decisions.md")))
            self.assertIn("corrupted", read(os.path.join(store, "errors.log")))

    def test_unsupported_newer_schema_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            staged = stage(tmp, "decision", "# Not written\n\nBody.\n")
            store = os.path.join(tmp, ".continuity")
            with open(os.path.join(store, "metadata.json"), "w", encoding="utf-8") as handle:
                json.dump({"schema_version": "9.0", "plugin_version": "9.0.0"}, handle)

            self.assertIsNone(write_memory(tmp, "file-change"))

            self.assertTrue(os.path.exists(staged), "a skipped store must not consume notes")
            self.assertFalse(os.path.exists(os.path.join(store, "decisions.md")))
            self.assertEqual(sessions_files(tmp), [])

    def test_cli_reports_both_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            writer = os.path.join(REPO_ROOT, "lib", "write_memory.py")

            empty = subprocess.run(
                [sys.executable, writer, tmp, "explicit-checkpoint"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )
            self.assertEqual(empty.returncode, 0, empty.stderr)
            self.assertIn("Nothing new to checkpoint", empty.stdout)

            stage(tmp, "decision", "# Something\n\nBody.\n")
            written = subprocess.run(
                [sys.executable, writer, tmp, "explicit-checkpoint"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
            )
            self.assertEqual(written.returncode, 0, written.stderr)
            self.assertIn("Checkpoint written to", written.stdout)
            self.assertEqual(len(sessions_files(tmp)), 1)


class TestCaptureTrigger(unittest.TestCase):
    def run_hook(self, payload):
        started = time.monotonic()
        result = subprocess.run(
            [sys.executable, CAPTURE_TRIGGER_HOOK],
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
        return result, time.monotonic() - started

    def wait_for_handoff(self, project_root, timeout=10.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if sessions_files(project_root):
                return True
            time.sleep(0.05)
        return False

    def test_whitespace_only_edit_writes_nothing_and_logs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Staged but untriggered\n\nBody.\n")
            result, _ = self.run_hook(
                {
                    "session_id": "s",
                    "cwd": tmp,
                    "tool_name": "Edit",
                    "tool_input": {
                        "file_path": os.path.join(tmp, "a.py"),
                        "old_string": "x = 1",
                        "new_string": "x  =  1",
                    },
                }
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            time.sleep(0.5)
            self.assertEqual(sessions_files(tmp), [])
            self.assertFalse(
                os.path.exists(os.path.join(tmp, ".continuity", "errors.log")),
                "a legitimate no-op is not a failure",
            )

    def test_meaningful_edit_reaches_the_detached_writer(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Captured by the trigger\n\nBody.\n")
            result, elapsed = self.run_hook(
                {
                    "session_id": "s",
                    "cwd": tmp,
                    "tool_name": "Edit",
                    "tool_input": {
                        "file_path": os.path.join(tmp, "a.py"),
                        "old_string": "x = 1",
                        "new_string": "x = 2",
                    },
                }
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertTrue(self.wait_for_handoff(tmp), "no handoff file appeared")
            self.assertIn(
                "Captured by the trigger",
                read(os.path.join(tmp, ".continuity", "decisions.md")),
            )
            # Not the sub-100ms proof (that is T020's timing test, with its
            # own sleeping-stub margin) — this bound only has to fail if the
            # hook ever starts waiting for the writer it launched. Measured
            # locally at ~41 ms including interpreter startup.
            self.assertLess(elapsed, 0.25)

    def test_malformed_payload_exits_zero_and_launches_nothing(self):
        # Valid JSON that is not an object: `parsed.get("cwd")` would raise
        # straight out of the hook, which is itself a fail-open violation.
        result, _ = self.run_hook([1, 2, 3])

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_non_git_bash_call_is_not_a_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage(tmp, "decision", "# Staged but untriggered\n\nBody.\n")
            result, _ = self.run_hook(
                {
                    "session_id": "s",
                    "cwd": tmp,
                    "tool_name": "Bash",
                    "tool_input": {"command": "ls -la"},
                }
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            time.sleep(0.5)
            self.assertEqual(sessions_files(tmp), [])


# Modules that can reach the network. An LLM call has to go through one of
# these, so their absence from the whole reachable import graph is what makes
# "this path never calls a model" checkable rather than asserted (T021).
NETWORK_MODULES = frozenset(
    [
        "urllib", "urllib2", "http", "httplib", "socket", "ssl", "ftplib",
        "smtplib", "poplib", "imaplib", "telnetlib", "xmlrpc", "webbrowser",
        "requests", "httpx", "aiohttp", "urllib3", "websockets", "grpc",
        "anthropic", "openai",
    ]
)

# argv[0] values a Continuity script may legitimately launch: itself (the
# detached writer) or the repo's own VCS. Anything else is an external
# process this path is not allowed to depend on.
ALLOWED_EXECUTABLES = frozenset(["python", "python3", "python.exe", "git"])

LAUNCHERS = frozenset(["system", "popen", "execv", "execve", "execvp", "spawnv"])


def imported_modules(tree):
    """Every module name an AST imports, both `import x` and `from x import`."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def reachable_sources(entry):
    """`entry` plus every first-party module it transitively imports.

    A network call moved one file down into `lib/` would still be a network
    call on this path, so the check follows `lib.*` imports rather than
    stopping at the entry script.
    """
    seen = {}
    pending = [entry]
    while pending:
        path = pending.pop()
        if path in seen:
            continue
        with open(path, encoding="utf-8") as handle:
            tree = ast.parse(handle.read(), filename=path)
        seen[path] = tree
        for module in imported_modules(tree):
            if module.startswith("lib."):
                candidate = os.path.join(
                    REPO_ROOT, *module.split(".")[:2]
                ) + ".py"
                if os.path.isfile(candidate):
                    pending.append(candidate)
    return seen


class TestNoModelCallOnTheWritePath(unittest.TestCase):
    """T021 — no turn pays for an LLM call to persist or load memory.

    Neither the writer nor the session-start reader may summarize via a
    model: they have no network permission to do so (Q7), and a per-turn API
    call is exactly the cost User Story 2 exists to avoid. Static rather than
    behavioral, because the assertion is about what the code *cannot* do —
    a runtime test only proves the paths it happened to exercise.
    """

    ENTRY_POINTS = (
        os.path.join(REPO_ROOT, "lib", "write_memory.py"),
        os.path.join(REPO_ROOT, "hooks", "session-start.py"),
    )

    def test_no_network_capable_module_is_reachable(self):
        for entry in self.ENTRY_POINTS:
            for path, tree in reachable_sources(entry).items():
                for module in imported_modules(tree):
                    self.assertNotIn(
                        module.split(".")[0],
                        NETWORK_MODULES,
                        "{} imports {}, reachable from {}".format(
                            os.path.relpath(path, REPO_ROOT),
                            module,
                            os.path.basename(entry),
                        ),
                    )

    def test_no_external_process_other_than_python_or_git_is_launched(self):
        for entry in self.ENTRY_POINTS:
            for path, tree in reachable_sources(entry).items():
                where = os.path.relpath(path, REPO_ROOT)
                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    if not isinstance(node.func, ast.Attribute):
                        continue
                    if node.func.attr not in LAUNCHERS and not (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "subprocess"
                    ):
                        continue
                    self.assertTrue(
                        node.args, "{}: unrecognized process launch".format(where)
                    )
                    self.assertEqual(
                        sorted(self.executables(node.args[0]) - ALLOWED_EXECUTABLES),
                        [],
                        "{} launches a process that is neither python nor git".format(
                            where
                        ),
                    )

    def executables(self, argument):
        """The argv[0] candidates of a launch argument, as basenames.

        `sys.executable` is the running interpreter, so it is reported as
        `python3`; anything not statically decidable is reported verbatim so
        it fails the allow-list rather than passing unproven.
        """
        if isinstance(argument, (ast.List, ast.Tuple)):
            if not argument.elts:
                return {"<empty argv>"}
            argument = argument.elts[0]
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
            return {os.path.basename(argument.value.split()[0])}
        if (
            isinstance(argument, ast.Attribute)
            and argument.attr == "executable"
            and isinstance(argument.value, ast.Name)
            and argument.value.id == "sys"
        ):
            return {"python3"}
        return {"<not statically decidable>"}


if __name__ == "__main__":
    unittest.main()
