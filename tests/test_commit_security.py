"""Integration tests use only disposable repositories and synthetic credentials."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "scripts/commit_security.py"
SETUP = ROOT / "scripts/setup_security.py"
STATUS_HOOK = ROOT / "hooks/security_status.py"
HOOK_NAMES = ("pre-commit", "pre-merge-commit", "pre-applypatch")
# The v1 template as installed before <hook>.d steps existed; update must recognize it exactly.
V1_HOOK = """#!/bin/sh
# HQ commit security Git hook v1; managed by scripts/setup_security.py.
set -eu
hq_git_common_dir=$(git rev-parse --git-common-dir)
if ! command -v python3 >/dev/null 2>&1; then
  echo 'BLOCKED: Python 3 is required for HQ commit security' >&2
  exit 1
fi
if [ ! -f "$hq_git_common_dir/hq-commit-security/check.py" ]; then
  echo 'BLOCKED: HQ commit security scanner is missing; restore the installation' >&2
  exit 1
fi
exec python3 "$hq_git_common_dir/hq-commit-security/check.py"
"""


class SecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hq-security-tests-")
        self.repo = Path(self.tmp.name) / "repo with spaces"
        self.repo.mkdir()
        self.env = os.environ.copy()
        for key in list(self.env):
            if key.startswith("GIT_"):
                del self.env[key]
        self.env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
        self.git("init", "-q")
        self.git("config", "user.name", "Security Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "commit.gpgsign", "false")

    def tearDown(self):
        self.tmp.cleanup()

    def run_command(self, args, cwd=None, input=None, env=None):
        return subprocess.run(args, cwd=cwd or self.repo, input=input, capture_output=True, text=True, env=env or self.env)

    def git(self, *args):
        result = self.run_command(["git", *args])
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def write(self, name, content):
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode() if isinstance(content, str) else content)

    def stage(self, name, content):
        self.write(name, content)
        self.git("add", "--", name)

    def check(self, *args, cwd=None, env=None):
        return self.run_command([sys.executable, str(CHECK), *args], cwd=cwd, env=env)

    def setup_hook(self, action="install"):
        return self.run_command([sys.executable, str(SETUP), action])

    def add_step(self, name, script, hook="pre-commit"):
        path = self.repo / ".git/hooks" / f"{hook}.d" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\nset -eu\n" + script)
        path.chmod(0o755)
        return path

    def assert_blocked(self, result, rule, secret=None):
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(rule, result.stderr)
        if secret:
            self.assertNotIn(secret, result.stderr + result.stdout)

    def test_initial_safe_commit_and_empty_index(self):
        self.assertEqual(self.check().returncode, 0)
        self.stage("README.md", "Safe repository\n")
        self.assertEqual(self.setup_hook().returncode, 0)
        self.git("commit", "-qm", "initial")
        self.assertEqual(self.check().returncode, 0)

    def test_env_variants_and_template_contents(self):
        for name in (".env", "nested/.env.production", "dev.env", ".envrc", "dev.env.local"):
            with self.subTest(name=name):
                self.stage(name, "APP_MODE=production\n")
                self.assert_blocked(self.check(), "env-file")
                self.git("rm", "--cached", "--", name)
        for name in (".env.example", ".env.sample", ".env.template", "env/source.py"):
            self.stage(name, 'API_KEY="${API_KEY}"\n')
        self.assertEqual(self.check().returncode, 0)
        secret = "gh" + "p_" + "Ab3D" * 10
        self.stage(".env.example", "API_KEY=" + secret)
        self.assert_blocked(self.check(), "service-token", secret)

    def test_local_paths_and_shared_paths(self):
        paths = (
            "/Users" + "/private-person/project",
            "/home" + "/private-person/project",
            "C:" + "\\Users\\private-person\\project",
            "C:" + "\\\\Users\\\\private-person\\\\project",
            "/private/var" + "/folders/ab/private-build/file",
        )
        for value in paths:
            with self.subTest(path=value[:3]):
                self.stage("config.txt", value)
                self.assert_blocked(self.check(), "local-path", value)
        self.stage("config.txt", '/usr/bin/python3\n$HOME/project\n/Users/<user>/project\n')
        self.assertEqual(self.check().returncode, 0)

    def test_secret_forms(self):
        secrets = (
            "sk-" + "proj-" + "aB3c" * 12,
            "AK" + "IA" + "A1" * 8,
            "xox" + "b-" + "1234567890-" * 3,
            "-----BEGIN " + "PRIVATE KEY-----",
            'access_token="' + "not-a-real-credential-12345" + '"',
            '"api_key": "' + "not-a-real-credential-67890" + '"',
        )
        for value in secrets:
            with self.subTest(kind=value[:3]):
                self.stage("config.txt", value)
                result = self.check()
                self.assertEqual(result.returncode, 1)
                self.assertNotIn(value, result.stdout + result.stderr)
        self.stage("config.txt", 'password="your-password"\napi_key="<key>"\ntoken=""\nsecret=os.getenv("SECRET")\n')
        self.assertEqual(self.check().returncode, 0)

    def test_partial_staging_reads_index_not_worktree(self):
        value = "gh" + "p_" + "Ab3D" * 10
        self.stage("config.txt", value)
        self.write("config.txt", "safe\n")
        self.assert_blocked(self.check(), "service-token", value)
        self.git("add", "config.txt")
        self.write("config.txt", value)
        self.assertEqual(self.check().returncode, 0)

    def test_entire_changed_file_not_just_added_lines(self):
        value = "/Users" + "/private-person/project"
        self.stage("config.txt", value + "\nold\n")
        self.git("commit", "-qm", "fixture")
        self.stage("config.txt", value + "\nnew\n")
        self.assert_blocked(self.check(), "local-path", value)

    def test_rename_delete_and_control_characters(self):
        name = "space\tline\nfile.txt"
        self.stage(name, "safe\n")
        self.git("commit", "-qm", "fixture")
        self.git("mv", "--", name, ".env")
        self.assert_blocked(self.check(), "env-file")
        self.git("rm", "-f", "--", ".env")
        self.assertEqual(self.check().returncode, 0)
        self.stage(name, "/home" + "/private-person/project")
        result = self.check()
        self.assertIn('\\tline\\n', result.stderr)
        self.assertEqual(len(result.stderr.splitlines()), 2)

    def test_unscannable_and_encoded_text(self):
        self.stage("binary.dat", b"a\x00b")
        self.assert_blocked(self.check(), "unscannable")
        self.git("rm", "--cached", "binary.dat")
        self.stage("utf16.txt", ("/Users" + "/private-person/project").encode("utf-16"))
        self.assert_blocked(self.check(), "local-path")
        self.stage("utf16.txt", "safe".encode("utf-16"))
        self.stage("large.txt", b"a" * (10 * 1024 * 1024 + 1))
        self.assert_blocked(self.check(), "unscannable")

    def test_policy_is_staged_and_content_bound(self):
        value = "/Users" + "/private-person/project"
        self.stage("config.txt", value)
        entry = {"path": "config.txt", "rule": "local-path", "fingerprint": "sha256:" + hashlib.sha256(value.encode()).hexdigest(), "reason": "Synthetic fixture for path detection"}
        policy = json.dumps({"version": 1, "allow": [entry]})
        self.write(".hq/v2/security.json", policy)
        self.assert_blocked(self.check(), "local-path", value)
        self.git("add", ".hq/v2/security.json")
        self.assertEqual(self.check().returncode, 0)
        self.stage("config.txt", value + "-changed")
        self.assert_blocked(self.check(), "local-path")
        self.stage(".hq/v2/security.json", '{"version": 1, "allow": [{"rule": "local-path"}]}')
        self.assertEqual(self.check().returncode, 2)

    def test_fingerprints_and_binary_exception(self):
        self.stage("binary.dat", b"a\x00b")
        result = self.check("--fingerprints")
        oid = self.git("rev-parse", ":binary.dat").strip()
        self.assertIn("blob:" + oid, result.stderr)
        entry = {"path": "binary.dat", "rule": "unscannable", "fingerprint": "blob:" + oid, "reason": "Reviewed synthetic binary"}
        self.stage(".hq/v2/security.json", json.dumps({"version": 1, "allow": [entry]}))
        self.assertEqual(self.check().returncode, 0)

    def test_hook_blocks_commit_and_missing_payload(self):
        self.assertEqual(self.setup_hook().returncode, 0)
        self.stage(".env", "APP_MODE=production\n")
        result = self.run_command(["git", "commit", "-qm", "must fail"])
        self.assertNotEqual(result.returncode, 0)
        self.assertNotEqual(self.run_command(["git", "rev-parse", "--verify", "HEAD"]).returncode, 0)
        self.git("rm", "--cached", ".env")
        self.stage("safe.txt", "safe\n")
        shutil.rmtree(self.repo / ".git/hq-commit-security")
        self.assertNotEqual(self.run_command(["git", "commit", "-qm", "missing scanner"]).returncode, 0)

    def test_existing_hook_and_custom_hookspath_preserved(self):
        hook = self.repo / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 17\n")
        original = hook.read_bytes()
        self.assertEqual(self.setup_hook().returncode, 2)
        self.assertEqual(hook.read_bytes(), original)
        self.assertEqual(self.setup_hook("prepare").returncode, 0)
        self.assertEqual(hook.read_bytes(), original)
        self.git("config", "core.hooksPath", "custom-hooks")
        self.assertEqual(self.setup_hook().returncode, 2)
        self.assertEqual(self.git("config", "core.hooksPath").strip(), "custom-hooks")
        self.assertIn("external-hook-unverified", self.setup_hook("status").stdout)

    def test_update_preserves_edits_and_uninstall(self):
        self.assertEqual(self.setup_hook().returncode, 0)
        self.assertEqual(self.setup_hook("status").stdout.strip(), "ready")
        self.assertEqual(self.setup_hook("update").returncode, 0)
        scanner = self.repo / ".git/hq-commit-security/check.py"
        original = scanner.read_bytes()
        scanner.write_bytes(original + b"\n# local edit\n")
        self.assertEqual(self.setup_hook("update").returncode, 2)
        self.assertTrue(scanner.read_bytes().endswith(b"# local edit\n"))
        scanner.write_bytes(original)
        self.assertEqual(self.setup_hook("uninstall").returncode, 0)
        self.assertFalse((self.repo / ".git/hooks/pre-commit").exists())

    def test_symlinks_not_followed(self):
        target = Path(self.tmp.name) / "outside"
        target.write_text("preserve\n")
        (self.repo / ".git/hooks/pre-commit").symlink_to(target)
        self.assertEqual(self.setup_hook().returncode, 2)
        self.assertEqual(target.read_text(), "preserve\n")
        (self.repo / ".git/hooks/pre-commit").unlink()
        (self.repo / "link").symlink_to("/Users" + "/private-person/project")
        self.git("add", "link")
        self.assert_blocked(self.check(), "local-path")
        self.assertEqual(self.setup_hook().returncode, 0)
        external_hooks = Path(self.tmp.name) / "external-hooks"
        shutil.move(str(self.repo / ".git/hooks"), external_hooks)
        (self.repo / ".git/hooks").symlink_to(external_hooks, target_is_directory=True)
        original = (external_hooks / "pre-commit").read_bytes()
        self.assertEqual(self.setup_hook("uninstall").returncode, 2)
        self.assertEqual((external_hooks / "pre-commit").read_bytes(), original)

    def test_worktree_and_subdirectory(self):
        self.stage("safe.txt", "safe\n")
        self.git("commit", "-qm", "fixture")
        self.assertEqual(self.setup_hook().returncode, 0)
        linked = Path(self.tmp.name) / "linked worktree"
        self.git("worktree", "add", "-qb", "linked", str(linked))
        self.assertEqual(self.run_command([sys.executable, str(SETUP), "status"], cwd=linked).returncode, 0)
        (linked / ".env").write_text("APP_MODE=production\n")
        self.assertEqual(self.run_command(["git", "add", ".env"], cwd=linked).returncode, 0)
        self.assertNotEqual(self.run_command(["git", "commit", "-qm", "blocked"], cwd=linked).returncode, 0)
        nested = self.repo / "nested"
        nested.mkdir()
        self.assertEqual(self.check(cwd=nested).returncode, 0)

    def test_commit_a_and_only_use_git_alternate_index(self):
        self.stage("config.txt", "safe\n")
        self.git("commit", "-qm", "fixture")
        self.assertEqual(self.setup_hook().returncode, 0)
        value = "/home" + "/private-person/project"
        self.write("config.txt", value)
        self.assertEqual(self.check().returncode, 0)
        for args in (("-a",), ("--only", "config.txt")):
            result = self.run_command(["git", "commit", "-qm", "blocked", *args])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("local-path", result.stderr)

    def test_invalid_git_and_conflicted_index_fail(self):
        self.assertEqual(self.check(cwd=self.tmp.name).returncode, 2)
        self.stage("config.txt", "safe\n")
        oid = self.git("rev-parse", ":config.txt").strip()
        self.git("update-index", "--force-remove", "config.txt")
        result = self.run_command(["git", "update-index", "--index-info"], input=f"100644 {oid} 1\tconfig.txt\n100644 {oid} 2\tconfig.txt\n")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.check().returncode, 2)

    def unsafe_patch(self):
        self.stage("safe.txt", "safe\n")
        self.git("commit", "-qm", "fixture")
        base = self.git("branch", "--show-current").strip()
        original = self.git("rev-parse", "HEAD").strip()
        self.git("checkout", "-qb", "unsafe")
        self.stage(".env", "APP_MODE=production\n")
        self.git("commit", "-qm", "unsafe fixture")
        patch = self.git("format-patch", "-1", "--stdout")
        self.git("checkout", "-q", base)
        self.assertEqual(self.setup_hook().returncode, 0)
        return original, patch

    def test_automatic_merge_commit_is_blocked(self):
        original, _ = self.unsafe_patch()
        result = self.run_command(["git", "merge", "--no-ff", "--no-edit", "unsafe"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("env-file", result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), original)

    def test_git_am_commit_is_blocked(self):
        original, patch = self.unsafe_patch()
        result = self.run_command(["git", "am"], input=patch)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("env-file", result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), original)

    def test_submodule_and_binary_secret_are_not_silently_accepted(self):
        self.stage("safe.txt", "safe\n")
        self.git("commit", "-qm", "fixture")
        oid = self.git("rev-parse", "HEAD").strip()
        self.git("update-index", "--add", "--cacheinfo", f"160000,{oid},nested-module")
        self.assert_blocked(self.check(), "unscannable")
        self.git("update-index", "--force-remove", "nested-module")
        value = "gh" + "p_" + "Ab3D" * 10
        self.stage("binary.dat", b"\x00" + value.encode())
        result = self.check()
        self.assert_blocked(result, "service-token", value)
        self.assertIn("unscannable", result.stderr)

    def test_relative_alternate_index_from_subdirectory(self):
        nested = self.repo / "nested"
        nested.mkdir()
        alternate_env = self.env.copy()
        alternate_env["GIT_INDEX_FILE"] = str(nested / "index")
        self.write(".env", "APP_MODE=production\n")
        result = self.run_command(["git", "add", ".env"], env=alternate_env)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.check().returncode, 0)
        alternate_env["GIT_INDEX_FILE"] = "index"
        self.assert_blocked(self.check(cwd=nested, env=alternate_env), "env-file")

    def test_external_configuration_prevents_partial_uninstall(self):
        self.assertEqual(self.setup_hook().returncode, 0)
        hook = self.repo / ".git/hooks/pre-commit"
        original = hook.read_bytes()
        self.git("config", "core.hooksPath", "custom-hooks")
        self.assertEqual(self.setup_hook("uninstall").returncode, 2)
        self.assertEqual(hook.read_bytes(), original)
        self.assertTrue((self.repo / ".git/hq-commit-security/check.py").is_file())

    def test_steps_run_in_order_before_scan_of_resulting_index(self):
        self.stage("safe.txt", "safe\n")
        self.git("commit", "-qm", "fixture")
        self.assertEqual(self.setup_hook().returncode, 0)
        log = Path(self.tmp.name) / "steps.log"
        self.add_step("20-second", f'echo second >> "{log}"\n')
        self.add_step("10-first", f'echo first >> "{log}"\n')
        self.stage("safe.txt", "changed\n")
        self.git("commit", "-qm", "steps pass")
        self.assertEqual(log.read_text(), "first\nsecond\n")
        self.assertEqual(self.setup_hook("status").stdout.strip(), "ready")
        # A step may change the index; the scan must see that index, including Git's alternate ones.
        self.add_step("30-stage-env", "printf 'APP_MODE=production\\n' > .env\ngit add .env\n")
        for args in ((), ("-a",), ("--only", "safe.txt")):
            self.write("safe.txt", f"change {args}\n")
            if not args:
                self.git("add", "safe.txt")
            result = self.run_command(["git", "commit", "-qm", "blocked", *args])
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("env-file", result.stderr)
            self.git("rm", "-q", "--cached", "--ignore-unmatch", ".env")

    def test_failing_or_unrunnable_step_blocks_commit(self):
        self.assertEqual(self.setup_hook().returncode, 0)
        self.stage("safe.txt", "safe\n")
        step = self.add_step("10-fail", "echo step-message >&2\nexit 3\n")
        result = self.run_command(["git", "commit", "-qm", "blocked"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("step-message", result.stderr)
        self.assertIn("BLOCKED: pre-commit.d/10-fail failed", result.stderr)
        step.chmod(0o644)
        result = self.run_command(["git", "commit", "-qm", "blocked"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BLOCKED: pre-commit.d/10-fail is not an executable file", result.stderr)
        step.unlink()
        broken = step.parent / "10-link"
        broken.symlink_to(step.parent / "missing")
        result = self.run_command(["git", "commit", "-qm", "blocked"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BLOCKED: pre-commit.d/10-link is not an executable file", result.stderr)
        self.assertNotEqual(self.run_command(["git", "rev-parse", "--verify", "HEAD"]).returncode, 0)
        broken.unlink()
        (step.parent / ".DS_Store").write_text("ignored\n")
        self.git("commit", "-qm", "passes")

    def test_steps_for_merge_commits(self):
        self.stage("safe.txt", "safe\n")
        self.git("commit", "-qm", "fixture")
        self.git("switch", "-qc", "side")
        self.stage("side.txt", "side\n")
        self.git("commit", "-qm", "side")
        self.git("switch", "-q", "-")
        original = self.git("rev-parse", "HEAD").strip()
        self.assertEqual(self.setup_hook().returncode, 0)
        self.add_step("10-fail", "exit 1\n", hook="pre-merge-commit")
        result = self.run_command(["git", "merge", "--no-ff", "--no-edit", "side"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BLOCKED: pre-merge-commit.d/10-fail failed", result.stderr)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), original)

    def test_update_replaces_only_previous_hq_hooks(self):
        self.assertEqual(self.setup_hook().returncode, 0)
        hooks = self.repo / ".git/hooks"
        current = (hooks / "pre-commit").read_bytes()
        for name in HOOK_NAMES:
            (hooks / name).write_text(V1_HOOK)
        self.assertEqual(self.setup_hook("status").stdout.strip(), "update-available")
        self.assertEqual(self.setup_hook("update").returncode, 0)
        self.assertEqual(self.setup_hook("status").stdout.strip(), "ready")
        for name in HOOK_NAMES:
            self.assertEqual((hooks / name).read_bytes(), current)
        # A hand-edited hook is neither replaced nor accepted.
        edited = hooks / "pre-applypatch"
        edited.write_text(V1_HOOK + "# local edit\n")
        self.assertEqual(self.setup_hook("status").stdout.strip(), "hook-missing-or-modified")
        self.assertEqual(self.setup_hook("update").returncode, 0)
        self.assertTrue(edited.read_text().endswith("# local edit\n"))
        self.assertEqual(self.setup_hook("uninstall").returncode, 2)
        # Exact previous copies can be removed; repository-owned steps are kept.
        edited.write_text(V1_HOOK)
        step = self.add_step("10-keep", "exit 0\n")
        result = self.setup_hook("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Kept pre-commit.d/", result.stdout)
        self.assertTrue(step.is_file())
        for name in HOOK_NAMES:
            self.assertFalse((hooks / name).exists())

    def test_install_and_uninstall_are_repeatable(self):
        result = self.setup_hook("uninstall")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not installed", result.stdout)
        for _ in range(2):
            result = self.setup_hook()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("status=ready", result.stdout)
        hooks = self.repo / ".git/hooks"
        current = (hooks / "pre-commit").read_bytes()
        # An earlier HQ copy, a lost exec bit and a missing scanner copy all converge to ready.
        (hooks / "pre-commit").write_text(V1_HOOK)
        (hooks / "pre-merge-commit").chmod(0o644)
        shutil.rmtree(self.repo / ".git/hq-commit-security")
        self.assertEqual(self.setup_hook("status").stdout.strip(), "damaged")
        self.assertEqual(self.setup_hook().returncode, 0)
        self.assertEqual(self.setup_hook("status").stdout.strip(), "ready")
        for name in HOOK_NAMES:
            self.assertEqual((hooks / name).read_bytes(), current)
            self.assertTrue(os.access(hooks / name, os.X_OK))
        # A hand-edited hook still stops install before anything changes.
        edited = hooks / "pre-applypatch"
        edited.write_bytes(current + b"# local edit\n")
        self.assertEqual(self.setup_hook().returncode, 2)
        self.assertTrue(edited.read_bytes().endswith(b"# local edit\n"))
        edited.write_bytes(current)
        for _ in range(2):
            result = self.setup_hook("uninstall")
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not installed", result.stdout)
        self.assertFalse(any((hooks / name).exists() for name in HOOK_NAMES))
        # Exact HQ leftovers without the scanner copy are removed; other hooks are kept.
        (hooks / "pre-commit").write_bytes(current)
        other = hooks / "pre-merge-commit"
        other.write_text("#!/bin/sh\nexit 0\n")
        self.assertEqual(self.setup_hook("uninstall").returncode, 0)
        self.assertFalse((hooks / "pre-commit").exists())
        self.assertTrue(other.is_file())

    def session_start(self):
        event = json.dumps({"hook_event_name": "SessionStart", "cwd": str(self.repo)})
        result = self.run_command([sys.executable, str(STATUS_HOOK)], input=event)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(str(self.repo), result.stdout)
        if not result.stdout:
            return None
        message = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(message["hookEventName"], "SessionStart")
        return message["additionalContext"]

    def test_session_hook_reminds_only_declared_repositories(self):
        # Without a declaration, not installing is a valid choice.
        self.assertIsNone(self.session_start())
        self.write(".hq/v2/settings.json", json.dumps({"git": {}, "commitSecurity": {"required": True}}))
        self.assertIn("not-installed", self.session_start())
        local = ".hq/v2/.ignore/settings.json"
        self.write(local, json.dumps({"commitSecurity": {"required": False}}))
        self.assertIsNone(self.session_start())
        # A malformed declaration is reported instead of falling back silently.
        for content in ('{"commitSecurity": {"required": "yes"}}', "{", "[]"):
            self.write(local, content)
            self.assertIn('{"required": true}', self.session_start())
        (self.repo / local).unlink()
        self.assertFalse((self.repo / ".git/hq-commit-security").exists())
        self.assertEqual(self.setup_hook().returncode, 0)
        self.assertIsNone(self.session_start())
        # Breakage of an installed guard is reported regardless of the declaration.
        self.write(".hq/v2/settings.json", json.dumps({"commitSecurity": {"required": False}}))
        (self.repo / ".git/hooks/pre-applypatch").chmod(0o644)
        self.assertIn("hook-missing-or-modified", self.session_start())
        # Leftover HQ hooks without the scanner copy block commits, so they are not mere absence.
        (self.repo / ".hq/v2/settings.json").unlink()
        shutil.rmtree(self.repo / ".git/hq-commit-security")
        self.assertIn("damaged", self.session_start())


if __name__ == "__main__":
    unittest.main()
