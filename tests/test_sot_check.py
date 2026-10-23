"""The SOT check after PR creation is advisory and uses only disposable repositories and a fake gh."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "hooks/sot_check.py"
URL = "https://github.com/owner/repo/pull/7"
FAKE_GH = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
[ -n "$FAKE_GH_SLEEP" ] && exec sleep "$FAKE_GH_SLEEP"
[ -n "$FAKE_GH_FAIL" ] && { echo "HTTP 502" >&2; exit 1; }
printf '%s' "$FAKE_GH_JSON"
"""


class SotCheckHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hq-sot-hook-")
        base = Path(self.tmp.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        bin_dir = base / "bin"
        bin_dir.mkdir()
        (bin_dir / "gh").write_text(FAKE_GH)
        (bin_dir / "gh").chmod(0o755)
        self.log = base / "gh.log"
        self.env = {key: value for key, value in os.environ.items() if not key.startswith(("GIT_", "FAKE_GH_"))}
        self.env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "FAKE_GH_LOG": str(self.log),
                         "PATH": f"{bin_dir}{os.pathsep}{self.env.get('PATH', '')}"})
        self.git("init", "-q", "-b", "develop")
        self.git("config", "user.name", "Hook Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.git("remote", "add", "origin", "git@github.com:Owner/repo.git")
        self.write("docs/PRD.md", "# PRD\n")
        self.write("wip/20260901-earlier/status.json", {"status": "active", "sotImpact": False, "prs": []})
        self.commit("base with records")
        self.base = self.rev("develop")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args, cwd=None):
        result = subprocess.run(["git", *args], cwd=cwd or self.repo, capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def rev(self, name):
        return self.git("rev-parse", name).strip()

    def write(self, name, content, root=None):
        path = (root or self.repo) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content if isinstance(content, str) else json.dumps(content))

    def commit(self, message, root=None):
        self.git("add", "-A", cwd=root)
        self.git("commit", "-qm", message, cwd=root)

    def diverging_branch(self):
        """Commit an implementation-only change for a record that expects an SOT change; return its commit."""
        self.git("switch", "-qc", "feat")
        self.write("wip/20261001-impact/status.json", {"status": "active", "sotImpact": True, "prs": []})
        self.write("src/app.py", "change = 1\n")
        self.commit("implementation only")
        return self.rev("HEAD")

    def created(self, output=URL + "\n"):
        return {"tool_name": "Bash", "tool_input": {"command": "gh pr create --base develop"},
                "tool_response": {"stdout": output, "stderr": "", "interrupted": False}}

    def run_hook(self, event, cwd=None, gh=None, **env):
        """Run the hook; gh is the (head, base) that the fake gh reports."""
        event = {"hook_event_name": "PostToolUse", "cwd": str(cwd or self.repo), **event}
        head, base = gh or (self.rev("HEAD"), self.base)
        run_env = {**self.env, "FAKE_GH_JSON": json.dumps({"headRefOid": head, "baseRefOid": base}), **env}
        result = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True,
                                text=True, env=run_env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        if not result.stdout:
            return None
        output = json.loads(result.stdout)
        self.assertEqual(list(output), ["hookSpecificOutput"])
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PostToolUse")
        message = output["hookSpecificOutput"]["additionalContext"]
        self.assertNotIn(self.tmp.name, message)
        return message

    def test_other_events_and_tools_are_ignored(self):
        head = self.diverging_branch()
        self.assertIsNone(self.run_hook({**self.created(), "hook_event_name": "PreToolUse"}, gh=(head, self.base)))
        self.assertIsNone(self.run_hook({**self.created(), "tool_input": {"command": "git push -u origin feat"}}))
        self.assertIsNone(self.run_hook({"tool_name": "Edit", "tool_input": {"file_path": "x"}, "tool_response": URL}))
        self.assertFalse(self.log.exists())

    def test_divergence_in_the_created_pr_is_reported(self):
        head = self.diverging_branch()
        message = self.run_hook(self.created(), gh=(head, self.base))
        self.assertIn("sot-not-updated", message)
        self.assertIn("20261001-impact", message)
        self.assertIn(URL, message)
        self.assertEqual(self.log.read_text().split(), ["pr", "view", URL, "--json", "headRefOid,baseRefOid"])
        mcp = {"tool_name": "mcp__github__create_pull_request", "tool_input": {"base": "develop", "head": "feat"},
               "tool_response": [{"type": "text", "text": json.dumps({"html_url": URL, "number": 7})}]}
        self.assertIn("sot-not-updated", self.run_hook(mcp, gh=(head, self.base)))
        self.write("docs/PRD.md", "# PRD\nupdated\n")
        self.commit("sot updated")
        self.assertIsNone(self.run_hook(self.created()))

    def test_the_pr_commits_decide_not_the_checkout(self):
        head = self.diverging_branch()
        # Another branch checked out, and an uncommitted setting that would hide the finding.
        self.git("switch", "-qc", "other", "develop")
        self.write(".hq/v2/settings.json", {"sdd": {"path": "src"}})
        self.assertIn("sot-not-updated", self.run_hook(self.created(), gh=(head, self.base)))
        # A separate work tree shares the objects, so the main checkout can check its PR.
        tree = Path(self.tmp.name) / "trees" / "fix"
        self.git("worktree", "add", "-q", "-b", "fix", str(tree), "develop")
        self.write("wip/20261002-fix/status.json", {"status": "active", "sotImpact": True, "prs": []}, root=tree)
        self.write("src/fix.py", "fixed = 1\n", root=tree)
        self.commit("fix implementation", root=tree)
        message = self.run_hook(self.created(), gh=(self.git("rev-parse", "HEAD", cwd=tree).strip(), self.base))
        self.assertIn("20261002-fix", message)
        self.assertNotIn("20261001-impact", message)

    def test_results_that_cannot_be_tied_to_commits_are_reported_as_not_checked(self):
        head = self.diverging_branch()
        missing = "0" * 40
        cases = (
            ("no URL", self.created("could not create pull request\n"), {}, (head, self.base)),
            ("two PRs", self.created(f"{URL}\nhttps://github.com/owner/repo/pull/8\n"), {}, (head, self.base)),
            ("other repository", self.created("https://github.com/someone/repo/pull/7\n"), {}, (head, self.base)),
            ("gh failure", self.created(), {"FAKE_GH_FAIL": "1"}, (head, self.base)),
            ("invalid gh output", self.created(), {"FAKE_GH_JSON": "not json"}, (head, self.base)),
            ("missing head", self.created(), {}, (missing, self.base)),
            ("missing base", self.created(), {}, (head, missing)),
        )
        for label, event, env, commits in cases:
            with self.subTest(label):
                message = self.run_hook(event, gh=commits, **env)
                self.assertIsNotNone(message)
                self.assertTrue(message.startswith("HQ SOT check not run:"), message)
                self.assertNotIn("sot-not-updated", message)

    def test_same_commits_in_another_repository_are_not_checked(self):
        head = self.diverging_branch()
        clone = Path(self.tmp.name) / "clone"
        self.git("clone", "-q", str(self.repo), str(clone))
        self.git("remote", "set-url", "origin", "https://github.com/someone/fork.git", cwd=clone)
        message = self.run_hook(self.created(), cwd=clone, gh=(head, self.base))
        self.assertTrue(message.startswith("HQ SOT check not run:"), message)
        self.assertIn("no remote for the pull request's repository", message)

    def test_gh_timeout_is_not_checked(self):
        spec = importlib.util.spec_from_file_location("sot_check_hook", HOOK)
        hook = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(hook)
        self.diverging_branch()
        event = {"hook_event_name": "PostToolUse", "cwd": str(self.repo), **self.created()}
        started = time.monotonic()
        with patch.dict(os.environ, {**self.env, "FAKE_GH_SLEEP": "5"}, clear=True), patch.object(hook, "GH_TIMEOUT", 0.5):
            message = hook.handle(event)["hookSpecificOutput"]["additionalContext"]
        self.assertLess(time.monotonic() - started, 4)
        self.assertTrue(message.startswith("HQ SOT check not run:"), message)
        self.assertIn("could not be retrieved", message)

    def test_repositories_without_records_stay_quiet(self):
        self.git("rm", "-rq", "wip")
        self.commit("no records")
        self.base = self.rev("develop")
        self.git("switch", "-qc", "feat")
        self.write("docs/PRD.md", "# PRD\nchanged\n")
        self.commit("docs only")
        self.assertIsNone(self.run_hook(self.created()))
        self.assertIsNone(self.run_hook(self.created("no URL\n")))
        plain = Path(self.tmp.name) / "plain"
        plain.mkdir()
        self.assertIsNone(self.run_hook(self.created(), cwd=plain))

    def test_invalid_settings_in_the_pr_are_reported(self):
        self.diverging_branch()
        self.write(".hq/v2/settings.json", {"sdd": {"path": "../outside"}})
        self.commit("bad setting")
        self.assertIn("sdd.path", self.run_hook(self.created()))


if __name__ == "__main__":
    unittest.main()
