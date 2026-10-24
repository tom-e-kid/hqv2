"""PR creation is gated before side effects; use disposable repos and a fake GitHub CLI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / 'hooks/pr_preflight.py'


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='hq-preflight-')
        self.repo = Path(self.tmp.name) / 'repo with spaces'
        self.repo.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull)
        self.git('init', '-q', '-b', 'develop')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        self.git('config', 'commit.gpgsign', 'false')
        self.git('remote', 'add', 'origin', 'git@github.com:owner/repo.git')
        self.write('README.md', 'base\n')
        self.commit()
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.git('switch', '-qc', 'feat')
        bin_dir = Path(self.tmp.name) / 'bin'
        bin_dir.mkdir()
        gh = bin_dir / 'gh'
        gh.write_text('''#!/usr/bin/env python3
import json, os, sys
if os.environ.get('GH_FAIL'): sys.exit(1)
ref = sys.argv[-1]
print(json.dumps({'object': {'sha': os.environ['BASE' if ref.endswith('/develop') else 'HEAD_SHA']}}))
''')
        gh.chmod(0o755)
        self.env['PATH'] = str(bin_dir) + os.pathsep + self.env.get('PATH', '')

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        r = subprocess.run(['git', *args], cwd=self.repo, env=self.env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def write(self, path, value):
        p = self.repo / path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value if isinstance(value, str) else json.dumps(value))

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'test')

    def record(self, state='active', path='wip/task'):
        self.write(path + '/status.json', {'status': state, 'ssotImpact': True, 'prs': []})
        self.write(path + '/work.md', '# Goal\nWork remains\n')
        self.commit()

    def run_hook(self, command=None, event=None, **env):
        payload = {'hook_event_name': 'PreToolUse', 'tool_name': 'Bash', 'cwd': str(self.repo),
                   'tool_input': {'command': command or 'gh pr create --repo owner/repo --base develop --head feat --title test --body test'}}
        if event:
            payload.update(event)
        r = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                           env={**self.env, 'BASE': self.base, 'HEAD_SHA': self.git('rev-parse', 'HEAD').strip(), **env})
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)['hookSpecificOutput'] if r.stdout else None

    def review(self, reason='Intermediate PR: remaining tasks belong to the next PR', **env):
        return subprocess.run([sys.executable, str(HOOK), '--repo', str(self.repo), '--repository', 'owner/repo',
                               '--base', 'develop', '--head', 'feat', '--reviewed', '--reason', reason],
                              capture_output=True, text=True, env={**self.env, 'BASE': self.base,
                              'HEAD_SHA': self.git('rev-parse', 'HEAD').strip(), **env})

    def denied(self, result):
        self.assertIsNotNone(result)
        self.assertEqual(result['hookEventName'], 'PreToolUse')
        self.assertEqual(result['permissionDecision'], 'deny')
        return result['permissionDecisionReason']

    def test_active_stops_and_review_allows_intermediate_pr(self):
        self.record()
        before = self.git('status', '--porcelain')
        message = self.denied(self.run_hook())
        self.assertIn('wip/task', message)
        self.assertIn('active', message)
        self.assertEqual(self.review().returncode, 0)
        self.assertIsNone(self.run_hook())
        self.assertEqual(self.git('status', '--porcelain'), before)
        self.assertEqual(json.loads((self.repo / 'wip/task/status.json').read_text())['status'], 'active')

    def test_new_head_invalidates_review(self):
        self.record()
        self.assertEqual(self.review().returncode, 0)
        self.write('README.md', 'changed\n')
        self.commit()
        self.denied(self.run_hook())

    def test_new_base_invalidates_review(self):
        self.record()
        self.assertEqual(self.review().returncode, 0)
        old_head = self.git('rev-parse', 'HEAD').strip()
        self.git('switch', 'develop')
        self.write('base.txt', 'new base')
        self.commit()
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.git('switch', 'feat')
        self.assertEqual(self.git('rev-parse', 'HEAD').strip(), old_head)
        self.denied(self.run_hook())

    def test_done_and_no_records_are_quiet(self):
        self.assertIsNone(self.run_hook())
        self.record('done')
        self.assertIsNone(self.run_hook())

    def test_paused_requires_review(self):
        self.record('paused')
        self.denied(self.run_hook())

    def test_invalid_status_cannot_be_acknowledged(self):
        self.record()
        self.write('wip/task/status.json', '{broken')
        self.commit()
        self.assertNotEqual(self.review().returncode, 0)
        self.denied(self.run_hook())

    def test_missing_status_and_custom_record_path(self):
        self.write('.hq/v2/settings.json', {'wip': {'path': 'records'}})
        self.write('records/task/work.md', '# Record')
        self.commit()
        self.assertIn('status.json', self.denied(self.run_hook()))
        self.record(path='records/task')
        self.assertIn('records/task', self.denied(self.run_hook()))

    def test_remote_failure_and_unknown_object_stop(self):
        self.record('done')
        self.denied(self.run_hook(GH_FAIL='1'))
        self.denied(self.run_hook(HEAD_SHA='a' * 40))

    def test_explicit_target_required_and_complex_shell_is_not_guessed(self):
        self.record()
        for command in ('gh pr create', 'cd elsewhere && gh pr create --repo owner/repo --base develop --head feat',
                        'gh pr create --repo owner/repo --base develop --head feat; echo ok',
                        'gh pr create --repo owner/repo --base develop --head "$BRANCH"'):
            with self.subTest(command=command):
                self.denied(self.run_hook(command))

    def test_mcp_uses_target_not_current_branch(self):
        self.record()
        event = {'tool_name': 'mcp__github__create_pull_request',
                 'tool_input': {'owner': 'owner', 'repo': 'repo', 'base': 'develop', 'head': 'feat'}}
        self.denied(self.run_hook(event=event))
        self.assertEqual(self.review().returncode, 0)
        self.git('switch', 'develop')
        self.assertIsNone(self.run_hook(event=event, HEAD_SHA=self.git('rev-parse', 'feat').strip()))

    def test_other_repository_is_unchecked(self):
        self.denied(self.run_hook('gh pr create --repo other/repo --base develop --head feat'))

    def test_other_tools_and_events_do_nothing(self):
        self.assertIsNone(self.run_hook('git status'))
        self.assertIsNone(self.run_hook('echo gh pr create'))
        self.assertIsNone(self.run_hook("echo 'gh pr create'"))
        self.assertIsNone(self.run_hook("cat > example.py <<'PY'\n# gh pr create\nPY"))
        self.assertIsNone(self.run_hook(event={'hook_event_name': 'PostToolUse'}))

    def test_blank_reason_is_rejected(self):
        self.record()
        self.assertNotEqual(self.review(' ').returncode, 0)

    def test_deleted_record_is_not_a_pending_work(self):
        self.record()
        self.base = self.git('rev-parse', 'HEAD').strip()
        self.git('rm', '-r', 'wip')
        self.commit()
        self.assertIsNone(self.run_hook())

    def test_connector_full_name_and_aliases(self):
        self.record()
        self.denied(self.run_hook(event={'tool_name': 'mcp__codex_apps__github_create_pull_request',
            'tool_input': {'repository_full_name': 'owner/repo', 'base_branch': 'develop', 'head_branch': 'feat'}}))

    def test_quoted_body_is_not_interpreted_as_shell(self):
        self.record('done')
        self.assertIsNone(self.run_hook('gh pr create -R owner/repo -B develop -H feat --body "example; text"'))

    def test_operators_attached_to_values_are_not_accepted(self):
        self.record('done')
        self.denied(self.run_hook('gh pr create -R owner/repo -B develop -H feat --body test;true'))

    def test_explicit_absolute_cli_path(self):
        self.record('done')
        self.assertIsNone(self.run_hook('/usr/local/bin/gh pr create -R owner/repo -B develop -H feat'))

    def test_invalid_settings_do_not_fall_back(self):
        self.write('.hq/v2/settings.json', {'wip': {'path': '../outside'}})
        self.commit()
        self.denied(self.run_hook())
        self.assertNotEqual(self.review().returncode, 0)

    def test_corrupt_receipt_and_changed_identity_require_review(self):
        self.record()
        self.assertEqual(self.review().returncode, 0)
        storage = Path(self.git('rev-parse', '--git-path', 'hq/pr-preflight').strip())
        if not storage.is_absolute():
            storage = self.repo / storage
        for p in storage.glob('*.json'):
            p.write_text('{broken')
        self.denied(self.run_hook())
        self.assertEqual(self.review().returncode, 0)
        self.git('remote', 'set-url', 'origin', 'git@enterprise.invalid:owner/repo.git')
        self.denied(self.run_hook())

    def test_worktree_decisions_are_separate(self):
        self.record()
        self.assertEqual(self.review().returncode, 0)
        other = Path(self.tmp.name) / 'other'
        self.git('worktree', 'add', '--detach', str(other), 'HEAD')
        self.denied(self.run_hook(event={'cwd': str(other)}))
