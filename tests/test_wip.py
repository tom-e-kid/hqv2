"""Work record listing and deletion checks use only disposable repositories."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/wip.py"


class WipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hq-wip-tests-")
        self.repo = Path(self.tmp.name) / "repo with spaces"
        self.repo.mkdir()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        self.git("init", "-q", "-b", "develop")
        self.git("config", "user.name", "Wip Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write("README.md", "base\n")
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

    def record(self, name, status="active", weight=2, prs=(), root="wip"):
        self.write(f"{root}/{name}/status.json", {"status": status, "weight": weight, "prs": list(prs)})
        self.write(f"{root}/{name}/work.md", f"# {name}\n")

    def run_script(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), *args, "--repo", str(self.repo), "--json"],
                                capture_output=True, text=True, env=self.env)
        return result

    def results(self, *args):
        result = self.run_script(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return {row["name"]: row for row in json.loads(result.stdout)}

    def test_list_reports_states_and_problems(self):
        self.assertEqual(self.results("list"), {})
        self.record("20261001-active", prs=[3])
        self.record("20261002-done", status="done", weight=3)
        self.write("wip/20261003-missing/work.md", "# missing\n")
        self.write("wip/20261004-broken/status.json", "{")
        self.write("wip/20261005-weight/status.json", {"status": "active", "weight": 4, "prs": []})
        self.write("wip/20261006-prs/status.json", {"status": "paused", "weight": 1, "prs": ["#3"]})
        self.write("wip/20261007-status/status.json", {"status": "finished", "weight": 1})
        self.write("wip/notes.md", "not a record\n")
        rows = self.results("list")
        self.assertEqual(rows["20261001-active"]["status"], {"status": "active", "weight": 2, "prs": [3]})
        self.assertIsNone(rows["20261002-done"]["problem"])
        self.assertIn("missing", rows["20261003-missing"]["problem"])
        self.assertIn("JSON", rows["20261004-broken"]["problem"])
        self.assertIn("weight", rows["20261005-weight"]["problem"])
        self.assertIn("prs", rows["20261006-prs"]["problem"])
        self.assertIn("status", rows["20261007-status"]["problem"])
        self.assertNotIn("notes.md", rows)

    def test_configured_path_and_invalid_settings(self):
        self.record("20261001-custom", root="work/records")
        self.write(".hq/v2/settings.json", {"wip": {"path": "work/records"}})
        self.assertEqual(list(self.results("list")), ["20261001-custom"])
        for value in ("../outside", "/abs", "", 3):
            self.write(".hq/v2/settings.json", {"wip": {"path": value}})
            result = self.run_script("list")
            self.assertEqual(result.returncode, 2)
            self.assertIn("wip.path", result.stderr)
        self.write(".hq/v2/settings.json", "{")
        self.assertEqual(self.run_script("list").returncode, 2)

    def test_done_record_is_deletable_only_after_it_reaches_the_base(self):
        self.record("20261001-task")
        self.commit("start")
        self.git("switch", "-qc", "feat")
        self.write("src.txt", "change\n")
        self.record("20261001-task", status="done", prs=[7])
        self.commit("finish")
        self.assertEqual(self.results("sweepable", "--base", "develop")["20261001-task"]["result"], "waiting")
        # A squash merge still carries the done state, so the later deletion is safe.
        self.git("switch", "-q", "develop")
        self.git("merge", "-q", "--squash", "feat")
        self.git("commit", "-qm", "squash feat")
        self.assertEqual(self.results("sweepable", "--base", "develop")["20261001-task"]["result"], "deletable")

    def test_later_edits_reopening_and_invalid_records_are_kept(self):
        self.record("20261001-edited", status="done")
        self.record("20261002-reopened", status="done")
        self.record("20261003-active")
        self.write("wip/20261004-missing/work.md", "# missing\n")
        self.commit("records")
        self.write("wip/20261001-edited/work.md", "# edited after merge\n")
        self.record("20261002-reopened", status="active")
        rows = self.results("sweepable", "--base", "develop")
        self.assertEqual(rows["20261001-edited"]["result"], "changed")
        self.assertEqual(rows["20261002-reopened"]["result"], "not-done")
        self.assertEqual(rows["20261003-active"]["result"], "not-done")
        self.assertEqual(rows["20261004-missing"]["result"], "invalid")
        self.git("checkout", "--", "wip/20261001-edited/work.md")
        # Untracked, ignored and hidden files would be lost by deleting the directory.
        self.write(".gitignore", "*.local\n")
        self.commit("ignore local files")
        for extra in ("extra.md", "evidence.local", "notes/.hidden"):
            path = self.repo / "wip/20261001-edited" / extra
            self.write(path.relative_to(self.repo).as_posix(), "unsaved\n")
            self.assertEqual(self.results("sweepable", "--base", "develop")["20261001-edited"]["result"], "changed", extra)
            path.unlink()
        self.assertEqual(self.results("sweepable", "--base", "develop")["20261001-edited"]["result"], "deletable")

    def test_base_revision_and_repository_are_required(self):
        self.assertEqual(self.run_script("sweepable").returncode, 2)
        result = self.run_script("sweepable", "--base", "origin/missing")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Base revision", result.stderr)
        outside = Path(self.tmp.name) / "plain"
        outside.mkdir()
        result = subprocess.run([sys.executable, str(SCRIPT), "list", "--repo", str(outside)],
                                capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 2)

    def test_text_output_lists_records(self):
        self.record("20261001-task", prs=[3, 4])
        result = subprocess.run([sys.executable, str(SCRIPT), "list", "--repo", str(self.repo)],
                                capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("20261001-task", result.stdout)
        self.assertIn("#3,#4", result.stdout)
        self.assertNotIn(str(self.repo), result.stdout)


if __name__ == "__main__":
    unittest.main()
