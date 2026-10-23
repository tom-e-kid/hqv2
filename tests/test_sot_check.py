"""The PR-creation SOT check hook is advisory and uses only disposable repositories."""

import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks/sot_check.py"


class SotCheckHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hq-sot-hook-")
        self.repo = Path(self.tmp.name) / "repo"
        self.repo.mkdir()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        self.git("init", "-q", "-b", "develop")
        self.git("config", "user.name", "Hook Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write("docs/PRD.md", "# PRD\n")
        self.commit("base")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.repo, capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content))

    def commit(self, message):
        self.git("add", "-A")
        self.git("commit", "-qm", message)

    def diverging_branch(self):
        self.git("switch", "-qc", "feat")
        self.write("wip/20261001-impact/status.json", {"status": "active", "sotImpact": True, "prs": []})
        self.write("src/app.py", "change = 1\n")
        self.commit("implementation only")

    def run_hook(self, event):
        event = {"hook_event_name": "PreToolUse", "cwd": str(self.repo), **event}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True,
                                text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        if not result.stdout:
            return None
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        self.assertNotIn("permissionDecision", output)
        return output["additionalContext"]

    def bash(self, command):
        return {"tool_name": "Bash", "tool_input": {"command": command}}

    def test_other_tools_and_commands_are_ignored(self):
        self.diverging_branch()
        self.assertIsNone(self.run_hook(self.bash("git push -u origin feat")))
        self.assertIsNone(self.run_hook({"tool_name": "Edit", "tool_input": {"file_path": "x"}}))
        self.assertIsNone(self.run_hook({**self.bash("gh pr create --base develop"), "hook_event_name": "PostToolUse"}))

    def test_divergence_is_reported_without_blocking(self):
        self.diverging_branch()
        message = self.run_hook(self.bash("git push && gh pr create --base develop --title x --body y"))
        self.assertIn("sot-not-updated", message)
        self.assertIn("20261001-impact", message)
        self.assertNotIn(str(self.repo), message)
        mcp = {"tool_name": "mcp__github__create_pull_request", "tool_input": {"base": "develop", "head": "feat"}}
        self.assertIn("sot-not-updated", self.run_hook(mcp))
        self.write("docs/PRD.md", "# PRD\nupdated\n")
        self.commit("sot updated")
        self.assertIsNone(self.run_hook(self.bash("gh pr create --base=develop")))

    def test_base_comes_from_the_branch_record_or_defaults(self):
        self.diverging_branch()
        self.write(".hq/v2/.ignore/settings.json", {"git": {"branches": {"feat": {"remote": "none", "baseBranch": "develop"}}}})
        self.assertIn("sot-not-updated", self.run_hook(self.bash("gh pr create")))
        (self.repo / ".hq/v2/.ignore/settings.json").unlink()
        self.write(".hq/v2/settings.json", {"git": {"baseBranch": "develop"}})
        self.commit("shared default")
        self.assertIn("sot-not-updated", self.run_hook(self.bash("gh pr create")))

    def test_unknown_base_is_reported_only_where_records_exist(self):
        self.diverging_branch()
        message = self.run_hook(self.bash("gh pr create"))
        self.assertIn("could not be determined", message)
        plain = Path(self.tmp.name) / "plain"
        plain.mkdir()
        self.assertIsNone(self.run_hook({**self.bash("gh pr create"), "cwd": str(plain)}))
        self.git("rm", "-rq", "wip")
        self.commit("no records")
        self.assertIsNone(self.run_hook(self.bash("gh pr create")))

    def work_tree(self):
        """Keep records on develop and diverge on a separate work tree, as HQ's worktree flow does."""
        self.write("wip/20260901-earlier/status.json", {"status": "active", "sotImpact": False, "prs": []})
        self.commit("records on the base")
        tree = Path(self.tmp.name) / "trees" / "feat"
        self.git("worktree", "add", "-q", "-b", "feat", str(tree))
        for name, content in (("wip/20261001-impact/status.json", json.dumps({"status": "active", "sotImpact": True, "prs": []})),
                              ("src/app.py", "change = 1\n")):
            (tree / name).parent.mkdir(parents=True, exist_ok=True)
            (tree / name).write_text(content)
        self.git("-C", str(tree), "add", "-A")
        self.git("-C", str(tree), "commit", "-qm", "implementation only")
        return tree

    def test_command_directory_is_followed(self):
        tree = self.work_tree()
        for command in (f"cd {shlex.quote(str(tree))} && gh pr create --base develop",
                        "cd ../trees/feat; git push -u origin feat && gh pr create --base develop"):
            self.assertIn("sot-not-updated", self.run_hook(self.bash(command)))
        mcp = {"tool_name": "mcp__github__create_pull_request", "tool_input": {"base": "develop", "head": "feat"}}
        self.assertIn("sot-not-updated", self.run_hook({**mcp, "cwd": str(tree)}))

    def test_unresolved_source_is_reported_as_not_checked(self):
        tree = self.work_tree()
        mcp = {"tool_name": "mcp__github__create_pull_request", "tool_input": {"base": "develop", "head": "feat"}}
        for event, reason in (
                (self.bash("gh pr create --base develop"), "no commits ahead"),
                (self.bash('cd "$TREE" && gh pr create --base develop'), "directory"),
                (self.bash(f"(cd {shlex.quote(str(tree))} && make) && gh pr create --base develop"), "directory"),
                (self.bash("gh pr create --head feat --base develop"), "PR head"),
                (mcp, "PR head"),
                (self.bash("gh pr create -R owner/repo --base develop"), "--repo"),
                (self.bash("gh pr create --body 'unbalanced"), "parsed")):
            message = self.run_hook(event)
            self.assertIn("not run", message)
            self.assertIn(reason, message)
            self.assertNotIn(str(self.repo), message)
        # A command that only mentions PR creation in its text does not create one.
        self.assertIsNone(self.run_hook(self.bash('git commit -m "gh pr create later"')))
        self.git("rm", "-rq", "wip")
        self.commit("no records")
        self.assertIsNone(self.run_hook(self.bash('cd "$TREE" && gh pr create --base develop')))

    def test_invalid_settings_are_reported(self):
        self.diverging_branch()
        self.write(".hq/v2/settings.json", {"sdd": {"path": "../outside"}})
        self.commit("bad setting")
        self.assertIn("sdd.path", self.run_hook(self.bash("gh pr create --base develop")))


if __name__ == "__main__":
    unittest.main()
