"""The PR-creation SOT check hook is advisory and uses only disposable repositories."""

import json
import os
from pathlib import Path
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

    def test_invalid_settings_are_reported(self):
        self.diverging_branch()
        self.write(".hq/v2/settings.json", {"sdd": {"path": "../outside"}})
        self.commit("bad setting")
        self.assertIn("sdd.path", self.run_hook(self.bash("gh pr create --base develop")))


if __name__ == "__main__":
    unittest.main()
