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

    def record(self, name, status="active", sot=False, prs=(), root="wip"):
        self.write(f"{root}/{name}/status.json", {"status": status, "ssotImpact": sot, "prs": list(prs)})
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
        self.record("20261002-done", status="done", sot=True)
        self.write("wip/20261003-missing/work.md", "# missing\n")
        self.write("wip/20261004-broken/status.json", "{")
        self.write("wip/20261005-impact/status.json", {"status": "active", "ssotImpact": "yes", "prs": []})
        self.write("wip/20261006-prs/status.json", {"status": "paused", "ssotImpact": False, "prs": ["#3"]})
        self.write("wip/20261007-status/status.json", {"status": "finished", "ssotImpact": True})
        self.write("wip/notes.md", "not a record\n")
        rows = self.results("list")
        self.assertEqual(rows["20261001-active"]["status"], {"status": "active", "ssotImpact": False, "prs": [3]})
        self.assertIsNone(rows["20261002-done"]["problem"])
        self.assertIn("missing", rows["20261003-missing"]["problem"])
        self.assertIn("JSON", rows["20261004-broken"]["problem"])
        self.assertIn("ssotImpact", rows["20261005-impact"]["problem"])
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
        # A staged edit stays unsaved even when the working file matches the base again.
        self.write("wip/20261001-edited/work.md", "# staged edit\n")
        self.git("add", "wip/20261001-edited/work.md")
        self.write("wip/20261001-edited/work.md", "# 20261001-edited\n")
        self.assertEqual(self.results("sweepable", "--base", "develop")["20261001-edited"]["result"], "changed")
        self.git("reset", "-q", "--", "wip/20261001-edited/work.md")
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

    def check(self, *args):
        result = self.run_script("check-pr", "--base", "develop", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def outcome(self):
        """Return (reminders, reasons the check cannot judge) in a comparable form."""
        result = self.check()
        return ([(item["code"], tuple(item["records"])) for item in result["notices"]],
                sorted((item["code"], item["record"]) for item in result["problems"]))

    def text(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), *args, "--repo", str(self.repo)],
                                capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def define_ssot(self, *paths):
        self.write(".hq/v2/settings.json", {"ssot": {"paths": list(paths)}})
        self.write("docs/PRD.md", "# PRD\n")
        self.commit("register the SSOT")

    def implementation_only(self, *records):
        for name, sot in records:
            self.record(name, sot=sot)
        self.write("src/app.py", "change = 1\n")
        self.commit("implementation only")

    def test_check_pr_does_not_apply_without_a_registered_ssot(self):
        # Locations and names do not define the SSOT, and AGENTS.md is not counted.
        self.write("docs/PRD.md", "# PRD\n")
        self.write("AGENTS.md", "# rules\n")
        self.commit("documents that are not registered")
        self.git("switch", "-qc", "feat")
        self.implementation_only(("20261001-impact", True))
        result = self.check()
        self.assertIsNone(result["ssotPaths"])
        self.assertEqual((result["notices"], result["problems"]), ([], []))
        self.assertIn("not defined", self.text("check-pr", "--base", "develop"))

    def test_check_pr_reminds_when_only_the_implementation_moves(self):
        self.define_ssot("docs")
        self.git("switch", "-qc", "feat")
        self.implementation_only(("20261001-impact", True), ("20261002-small", False))
        self.assertEqual(self.outcome(), ([("ssot-review", ("20261001-impact",))], []))
        detail = self.check()["notices"][0]["detail"]
        self.assertIn("not a consistency check", detail)
        self.assertNotIn("diverge", detail)
        # Updating the SSOT leaves the condition unmet; it does not confirm that the two agree.
        self.write("docs/PRD.md", "# PRD\nupdated\n")
        self.commit("SSOT updated")
        self.assertTrue(self.check()["ssotChanged"])
        self.assertEqual(self.outcome(), ([], []))
        self.assertIn("does not confirm", self.text("check-pr", "--base", "develop"))

    def test_check_pr_needs_an_impact_record_and_an_implementation_change(self):
        self.define_ssot("docs")
        cases = (
            ("lead", [("20261001-plan", True)], {"docs/PRD.md": "# PRD\nnext goal\n"}),
            ("record-only", [("20261001-plan", True)], {}),
            ("no-impact", [("20261002-small", False)], {"src/app.py": "change = 1\n"}),
            # No longer part of this check: an SSOT change without a record or with records that say no impact.
            ("ssot-without-record", [], {"docs/PRD.md": "# PRD\nchanged\n"}),
            ("ssot-without-impact", [("20261002-small", False)], {"docs/PRD.md": "# PRD\nchanged\n"}),
        )
        for branch, records, files in cases:
            with self.subTest(branch):
                self.git("switch", "-qc", branch, "develop")
                for name, sot in records:
                    self.record(name, sot=sot)
                for name, content in files.items():
                    self.write(name, content)
                self.commit(branch)
                self.assertEqual(self.outcome(), ([], []))

    def test_check_pr_reports_why_it_cannot_judge(self):
        self.define_ssot("docs")
        self.git("switch", "-qc", "feat")
        self.write("wip/20261001-broken/status.json", "{")
        self.write("wip/20261002-partial/work.md", "# partial\n")
        self.write("wip/.drafts/note.md", "not a record\n")
        self.implementation_only(("20261003-impact", True))
        # Readable records still lead to the reminder; unreadable ones are reported separately.
        self.assertEqual(self.outcome(), ([("ssot-review", ("20261003-impact",))],
                                          [("invalid-status", "20261001-broken"), ("invalid-status", "20261002-partial")]))
        details = {item["record"]: item["detail"] for item in self.check()["problems"]}
        self.assertEqual(details["20261002-partial"], "status.json is missing")
        # Registered paths must exist in the head commit; with none of them there is nothing to judge.
        self.write(".hq/v2/settings.json", {"ssot": {"paths": ["docs", "spec/ADD.md"]}})
        self.commit("register a document that does not exist")
        notices, problems = self.outcome()
        self.assertEqual(notices, [("ssot-review", ("20261003-impact",))])
        self.assertIn(("ssot-missing", None), problems)
        missing = [item["detail"] for item in self.check()["problems"] if item["code"] == "ssot-missing"]
        self.assertEqual(len(missing), 1)
        self.assertIn("spec/ADD.md", missing[0])
        self.write(".hq/v2/settings.json", {"ssot": {"paths": ["spec"]}})
        self.commit("register only missing paths")
        self.assertEqual(self.outcome(), ([], [("ssot-missing", None)]))

    def test_check_pr_counts_both_sides_of_a_move(self):
        self.define_ssot("docs")
        self.write("docs/ADD.md", "# ADD\n")
        self.commit("two SSOT documents")
        # Moving a document out of the SSOT changes the SSOT, even though Git reports it as a rename.
        self.git("switch", "-qc", "move-out")
        self.record("20261001-impact", sot=True)
        (self.repo / "archive").mkdir()
        self.git("mv", "docs/PRD.md", "archive/PRD.md")
        self.commit("move a document out of the SSOT")
        self.assertTrue(self.check()["ssotChanged"])
        self.assertEqual(self.outcome(), ([], []))
        # Moving an implementation file into the SSOT also changes both.
        self.git("switch", "-qc", "move-in", "develop")
        self.write("src/notes.md", "# notes\n")
        self.commit("implementation file")
        self.git("switch", "-qc", "move-in-pr")
        self.record("20261001-impact", sot=True)
        self.git("mv", "src/notes.md", "docs/notes.md")
        self.commit("move into the SSOT")
        result = self.check("--head", "move-in-pr", "--base", "move-in")
        self.assertEqual((result["ssotChanged"], result["implementationChanged"]), (True, True))

    def test_check_pr_reads_settings_from_the_head_commit(self):
        self.write(".hq/v2/settings.json", {"ssot": {"paths": ["spec", "README.md"]}, "wip": {"path": "spec/work"}})
        self.write("spec/PRD.md", "# PRD\n")
        self.commit("settings")
        self.git("switch", "-qc", "feat")
        self.record("20261001-impact", sot=True, root="spec/work")
        self.write("docs/notes.md", "not the SSOT here\n")
        self.commit("docs is ordinary content")
        # Records inside an SSOT directory are records, not SSOT changes.
        self.assertEqual(self.outcome(), ([("ssot-review", ("20261001-impact",))], []))
        self.write("README.md", "updated\n")
        self.commit("a registered file")
        self.assertEqual(self.outcome(), ([], []))
        # Only committed changes count, and a record removed by the change is skipped.
        self.git("switch", "-qc", "sweep", "develop")
        self.record("20261009-done", status="done", sot=True, root="spec/work")
        self.commit("done record")
        self.git("switch", "-q", "develop")
        self.git("merge", "-q", "--no-ff", "-m", "merge", "sweep")
        self.git("switch", "-qc", "cleanup")
        self.git("rm", "-rq", "spec/work/20261009-done")
        self.write("src/app.py", "change = 1\n")
        self.commit("sweep with an implementation change")
        self.write("src/uncommitted.py", "pending = 1\n")
        result = self.check()
        self.assertEqual((result["records"], result["notices"]), ([], []))
        # Settings come from the checked commit: an uncommitted change does not count, a committed one does.
        self.write(".hq/v2/settings.json", {"ssot": {"paths": ["."]}})
        self.assertEqual(self.outcome(), ([], []))
        for value in (["."], ["./"], ["../x"], ["/abs"], [], "spec", [""], [3]):
            self.write(".hq/v2/settings.json", {"ssot": {"paths": value}})
            self.commit(f"setting {value}")
            result = self.run_script("check-pr", "--base", "develop")
            self.assertEqual(result.returncode, 2, value)
            self.assertIn("ssot.paths", result.stderr)

    def test_check_pr_checks_the_given_head_commit(self):
        self.define_ssot("docs")
        self.git("switch", "-qc", "feat")
        self.implementation_only(("20261001-impact", True))
        head, base = self.git("rev-parse", "HEAD").strip(), self.git("rev-parse", "develop").strip()
        # The checkout no longer matters once the head is given; both ends are reported as commit IDs.
        self.git("switch", "-q", "develop")
        result = self.check("--head", "feat")
        self.assertEqual((result["base"], result["head"]), (base, head))
        self.assertEqual([item["code"] for item in result["notices"]], ["ssot-review"])
        self.assertEqual(self.check()["notices"], [])
        result = self.run_script("check-pr", "--base", "develop", "--head", "missing")
        self.assertEqual(result.returncode, 2)
        self.assertIn("Head revision", result.stderr)

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
