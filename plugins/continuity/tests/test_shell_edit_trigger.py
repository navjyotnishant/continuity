"""tests/test_shell_edit_trigger.py — what counts as an edit when it happens in the shell.

Before: only a Bash command containing the literal text `git commit`, or a `git` command in a
repo with a diff, counted. `git -c k=v commit` slipped past, and a file written with `>`, `sed -i`
or `mv` was invisible, so a turn of shell-only work never got its end-of-turn note request.
"""

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

REPO_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, REPO_ROOT)


def load_hook(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), os.path.join(REPO_ROOT, "hooks", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ct = load_hook("capture-trigger")


def bash(command, cwd="/r"):
    return {"hook_event_name": "PostToolUse", "tool_name": "Bash", "cwd": cwd, "tool_input": {"command": command}}


class TestGitCommitForms(unittest.TestCase):
    def test_commit_with_options_between_git_and_commit(self):
        for command in (
            "git commit -m x",
            "git -c user.name=t -c user.email=t@t commit -m x",
            "git -C /repo commit -am x",
            "git --no-pager commit",
            "git -c user.name='A B' commit -m x",
            'git -c user.name="A B" -c a=b commit',
            "git add -A && git -c k=v commit -m x",
        ):
            with self.subTest(command=command):
                self.assertTrue(ct._is_git_commit(command))
                self.assertEqual(ct.classify(bash(command)), "git-diff")

    def test_other_git_commands_are_not_commits(self):
        for command in ("git commit-tree abc", "git status", "git log --oneline", "echo git"):
            with self.subTest(command=command):
                self.assertFalse(ct._is_git_commit(command))


class TestShellWrites(unittest.TestCase):
    def test_commands_that_change_files(self):
        for command in (
            "echo x > a.py",
            "cat > f <<'EOF'\nhi\nEOF",
            "printf x >> f",
            "sed -i '' s/a/b/ f",
            "perl -pi -e s/a/b/ f",
            "echo x | tee f",
            "mv a b",
            "cp a b",
            "rm -f f",
            "touch f",
            "git checkout -- f",
            "python3 -c \"open('f','w').write('x')\"",
            "echo hi &> out.txt",
            "cd src && mv a b",
        ):
            with self.subTest(command=command):
                self.assertTrue(ct._writes_files(command))
                with mock.patch.object(ct, "_has_non_whitespace_diff", return_value=False):
                    self.assertIn(ct.classify(bash(command)), ("shell-edit", "git-diff"))

    def test_read_only_commands_are_not_edits(self):
        for command in (
            "ls -la",
            "cat f",
            "grep x f | head",
            "echo hi",
            "ls > /dev/null",
            "make 2>&1 | tail",
            "cmd 2>/dev/null",
            "cmd 2>err.log",
            "echo x > /tmp/scratch.txt",
            "git status",
            "git log --oneline",
            "cd d && ls",
            "python3 -m unittest",
            "npm test",
            "cat a | wc -l",
        ):
            with self.subTest(command=command):
                self.assertFalse(ct._writes_files(command))
                with mock.patch.object(ct, "_has_non_whitespace_diff", return_value=False):
                    self.assertIsNone(ct.classify(bash(command)))


class TestMarkingAndLaunching(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = self._tmp.name
        os.makedirs(os.path.join(self.root, ".continuity", ".staged"))
        self.marker = os.path.join(self.root, ".continuity", ".turn-edited")

    def tearDown(self):
        self._tmp.cleanup()

    def run_hook(self, command, diff=False):
        payload = bash(command, self.root)
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(payload))), mock.patch.object(
            ct, "launch_writer"
        ) as launch, mock.patch.object(ct, "_has_non_whitespace_diff", return_value=diff):
            ct.main()
        return launch

    def test_shell_edit_marks_the_turn_without_spawning_the_writer(self):
        launch = self.run_hook("echo x > a.py")
        self.assertTrue(os.path.exists(self.marker))
        launch.assert_not_called()

    def test_git_commit_marks_the_turn_and_launches_the_writer(self):
        launch = self.run_hook("git -c user.name=t commit -m x")
        self.assertTrue(os.path.exists(self.marker))
        launch.assert_called_once_with(self.root, "git-diff")

    def test_read_only_git_in_a_dirty_repo_launches_but_owes_no_note(self):
        launch = self.run_hook("git status", diff=True)
        launch.assert_called_once_with(self.root, "git-diff")
        self.assertFalse(os.path.exists(self.marker))

    def test_read_only_command_does_nothing(self):
        launch = self.run_hook("ls -la")
        launch.assert_not_called()
        self.assertFalse(os.path.exists(self.marker))

    def test_staging_a_note_from_the_shell_clears_the_marker(self):
        open(self.marker, "a").close()
        self.run_hook("mkdir -p .continuity/.staged && printf 'x' > .continuity/.staged/decision-1.md")
        self.assertFalse(os.path.exists(self.marker))


if __name__ == "__main__":
    unittest.main()
