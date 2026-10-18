"""Exercise externally visible batch limits, races, pagination and Hook wire behavior."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pr_feedback as pf

spec = importlib.util.spec_from_file_location('feedback_hook', Path(__file__).resolve().parents[1] / 'hooks/pr_feedback.py')
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


def comment(identifier='c1', author='reviewer', body='Bug', kind='comment'):
    return {'id': identifier, 'databaseId': 1, 'body': body, 'updatedAt': '2026-10-18T00:00:00Z', 'url': 'https://github.com/a/b/pull/1#' + identifier, 'author': {'login': author}}


def snapshot(body='Bug', complete=True):
    return {'viewer': 'owner', 'comments': [comment(body=body)] if body else [], 'reviewThreads': [],
            'reviews': [{'id': 'r1', 'body': '', 'commit': {'oid': 'head'}, 'author': {'login': 'reviewer'}, 'state': 'COMMENTED'}] if complete else []}


class FakeGitHub:
    def __init__(self):
        self.head = 'head'
        self.data = snapshot()
        self.writes = []
        self.fail_after_reply = False

    def pr(self, number):
        return {'number': number, 'head': self.head, 'branch': 'feature', 'repository': 'a/b', 'open': True, 'url': 'https://github.com/a/b/pull/1'}

    def snapshot(self, number):
        return self.data

    def api(self, endpoint, method='GET', payload=None):
        self.writes.append((endpoint, payload))
        reply = comment('own-reply', 'owner', payload['body'])
        if '/replies' in endpoint:
            self.data['reviewThreads'][0]['comments']['nodes'].append(reply)
        else:
            self.data['comments'].append(reply)
        if self.fail_after_reply:
            self.fail_after_reply = False
            raise pf.FeedbackError('ambiguous connection loss after successful POST')
        return {'html_url': reply['url']}

    def graphql(self, query, **variables):
        self.writes.append(('resolve', variables))
        self.data['reviewThreads'][0]['isResolved'] = True
        self.data['reviewThreads'][0]['viewerCanResolve'] = False
        return {'resolveReviewThread': {'thread': {'isResolved': True}}}


class MonitorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        subprocess.run(['git', 'init', '-b', 'feature', str(self.root)], capture_output=True, check=True)
        subprocess.run(['git', '-C', str(self.root), 'remote', 'add', 'origin', 'git@github.com:a/b.git'], check=True)
        path = self.root / '.hq/v2/pr-feedback.json'
        path.parent.mkdir(parents=True)
        self.config_path = path
        self.config = {'version': 1, 'enabled': True, 'repository': 'a/b', 'reviewers': ['reviewer'], 'quietSeconds': 0, 'waitSeconds': 5, 'actions': {'fix': True, 'push': True, 'reply': True, 'resolve': True}}
        path.write_text(json.dumps(self.config))
        self.monitor = pf.Monitor(self.root)
        self.fake = FakeGitHub()
        self.monitor.github = self.fake
        self.monitor.register(1, 'session')

    def report(self, result):
        report = [{'id': x['id'], 'decision': 'skip', 'reason': 'Verified existing behavior'} for x in result['items']]
        return self.monitor.respond(1, 'session', report)

    def test_three_batches_then_final_observation(self):
        for i in range(3):
            self.fake.data = snapshot('Bug ' + str(i))
            result = self.monitor.poll(1, 'session')
            self.assertEqual((result['status'], result['round']), ('batch', i + 1))
            # Re-entry resumes the same batch, not another round.
            self.assertEqual(self.monitor.poll(1, 'session')['round'], i + 1)
            self.monitor.finish(1, 'session', self.report(result))
        self.fake.data = snapshot('Still a bug')
        result = self.monitor.poll(1, 'session')
        self.assertEqual((result['reason'], result['round']), ('cap-reached', 3))
        self.assertEqual(len(result['items']), 1)
        # Explicit restart preserves cap and processed items.
        self.monitor.register(1, 'session')
        self.assertEqual(self.monitor.poll(1, 'session')['reason'], 'cap-reached')

    def test_replied_open_feedback_does_not_recur_without_changes(self):
        result = self.monitor.poll(1, 'session')
        self.monitor.finish(1, 'session', self.report(result))
        self.assertEqual(self.monitor.poll(1, 'session')['reason'], 'converged')

    def test_missing_review_is_timeout_not_convergence(self):
        self.fake.data = snapshot('', complete=False)
        self.assertEqual(self.monitor.poll(1, 'session')['status'], 'waiting')
        result = self.monitor.poll(1, 'session', now=10**12)
        self.assertEqual(result['reason'], 'wait-timeout')

    def test_unfinished_second_reviewer_waits_until_deadline(self):
        self.monitor.config['reviewers'].append('other-reviewer')
        self.assertEqual(self.monitor.poll(1, 'session')['status'], 'waiting')
        result = self.monitor.poll(1, 'session', now=10**12)
        self.assertEqual(result['status'], 'batch')
        self.assertFalse(result['reviewersComplete'])

    def test_unexpected_head_and_partial_report_do_not_complete_batch(self):
        result = self.monitor.poll(1, 'session')
        with self.assertRaises(pf.FeedbackError):
            self.monitor.finish(1, 'session', [])
        with self.assertRaises(pf.FeedbackError):
            self.monitor.finish(1, 'session', [{'id': 'c1', 'decision': 'skip', 'reason': 'why'}])
        report = self.report(result)
        self.fake.head = 'external'
        with self.assertRaises(pf.FeedbackError):
            self.monitor.finish(1, 'session', report)
        self.assertEqual(self.monitor.read(1)['status'], 'batch')

    def test_api_error_never_becomes_empty_feedback(self):
        self.fake.snapshot = lambda _: (_ for _ in ()).throw(pf.FeedbackError('offline'))
        with self.assertRaises(pf.FeedbackError):
            self.monitor.poll(1, 'session')
        self.assertEqual(self.monitor.read(1)['rounds'], 0)

    def test_other_session_and_lock_cannot_take_ownership(self):
        with self.assertRaises(pf.FeedbackError):
            self.monitor.register(1, 'other')
        with self.monitor.lock(1):
            with self.assertRaises(pf.FeedbackError):
                self.monitor.poll(1, 'session')

    def test_disabled_and_malformed_optin(self):
        self.config_path.write_text(json.dumps({'enabled': False}))
        self.assertIsNone(pf.Monitor(self.root).config)
        self.config_path.write_text(json.dumps(dict(self.config, maxRounds=True)))
        with self.assertRaises(pf.FeedbackError):
            pf.Monitor(self.root)

    def test_hook_register_continue_finish_and_report_once(self):
        event = {'hook_event_name': 'PostToolUse', 'session_id': 'session', 'cwd': str(self.root),
                 'tool_name': 'Bash', 'tool_input': {'command': 'gh pr create --body-file /tmp/body'},
                 'tool_response': {'output': 'https://github.com/a/b/pull/1'}}
        with patch.object(hook, 'Monitor', return_value=self.monitor):
            registered = hook.handle(event)
            self.assertEqual(registered['hookSpecificOutput']['hookEventName'], 'PostToolUse')
            stop = dict(event, hook_event_name='Stop', stop_hook_active=False)
            self.assertEqual(hook.handle(stop)['decision'], 'block')
            result = self.monitor.poll(1, 'session')
            self.monitor.finish(1, 'session', self.report(result))
            self.assertIn('converged', hook.handle(dict(stop, stop_hook_active=True))['reason'])
            self.assertIsNone(hook.handle(stop))

    def test_hook_incomplete_batch_does_not_loop(self):
        event = {'hook_event_name': 'Stop', 'session_id': 'session', 'cwd': str(self.root)}
        with patch.object(hook, 'Monitor', return_value=self.monitor):
            self.assertEqual(hook.handle(event)['decision'], 'block')
            self.assertIn('not completed', hook.handle(event)['reason'])
            self.assertIsNone(hook.handle(event))


    def test_reply_retries_reconcile_ambiguous_post(self):
        result = self.monitor.poll(1, 'session')
        self.fake.fail_after_reply = True
        with self.assertRaises(pf.FeedbackError):
            self.report(result)
        report = self.report(result)
        self.assertEqual(len(self.fake.writes), 1)
        self.monitor.finish(1, 'session', report)

    def test_resolve_reply_and_repeated_execution_are_idempotent(self):
        self.fake.data = snapshot('')
        self.fake.data['reviewThreads'] = [{'id': 'thread', 'isResolved': False, 'isOutdated': False,
            'viewerCanResolve': True, 'comments': {'nodes': [comment()]}}]
        self.monitor.poll(1, 'session')
        report = [{'id': 'thread', 'decision': 'skip', 'reason': 'Verified', 'resolve': True}]
        self.monitor.respond(1, 'session', report)
        self.monitor.respond(1, 'session', report)
        self.assertEqual(len(self.fake.writes), 2)
        self.assertTrue(report[0]['resolved'])
        self.monitor.finish(1, 'session', report)

    def test_action_permissions_and_deferred_resolve_are_enforced(self):
        self.monitor.poll(1, 'session')
        report = [{'id': 'c1', 'decision': 'defer', 'reason': 'Separate change', 'resolve': True}]
        with self.assertRaises(pf.FeedbackError):
            self.monitor.respond(1, 'session', report)
        self.monitor.config['actions']['reply'] = False
        report[0]['resolve'] = False
        with self.assertRaises(pf.FeedbackError):
            self.monitor.respond(1, 'session', report)
        self.assertEqual(self.fake.writes, [])

    def test_edit_after_triage_prevents_post(self):
        self.monitor.poll(1, 'session')
        self.fake.data = snapshot('Edited by reviewer')
        with self.assertRaises(pf.FeedbackError):
            self.monitor.respond(1, 'session', [{'id': 'c1', 'decision': 'skip', 'reason': 'Stale reasoning'}])
        self.assertEqual(self.fake.writes, [])

    def test_unverified_reply_url_cannot_finish(self):
        self.monitor.poll(1, 'session')
        with self.assertRaises(pf.FeedbackError):
            self.monitor.finish(1, 'session', [{'id': 'c1', 'decision': 'skip', 'reason': 'why', 'replyUrl': 'made-up'}])


    def test_reopened_resolved_thread_is_a_new_batch(self):
        self.fake.data = snapshot('')
        thread = {'id': 'thread', 'isResolved': False, 'isOutdated': False,
            'viewerCanResolve': True, 'comments': {'nodes': [comment()]}}
        self.fake.data['reviewThreads'] = [thread]
        self.monitor.poll(1, 'session')
        report = [{'id': 'thread', 'decision': 'skip', 'reason': 'Verified', 'resolve': True}]
        self.monitor.respond(1, 'session', report)
        self.monitor.finish(1, 'session', report)
        thread['isResolved'] = False
        thread['viewerCanResolve'] = True
        result = self.monitor.poll(1, 'session')
        self.assertEqual((result['status'], result['round']), ('batch', 2))
        self.monitor.respond(1, 'session', report)
        self.assertTrue(thread['isResolved'])
        self.assertEqual(len(self.fake.writes), 4)

    def test_human_reply_between_post_and_resolve_prevents_resolve(self):
        self.fake.data = snapshot('')
        thread = {'id': 'thread', 'isResolved': False, 'isOutdated': False,
            'viewerCanResolve': True, 'comments': {'nodes': [comment()]}}
        self.fake.data['reviewThreads'] = [thread]
        self.monitor.poll(1, 'session')
        original_api = self.fake.api
        def api(*args, **kwargs):
            response = original_api(*args, **kwargs)
            thread['comments']['nodes'].append(comment('human', 'someone', 'Please keep this open'))
            return response
        self.fake.api = api
        with self.assertRaises(pf.FeedbackError):
            self.monitor.respond(1, 'session', [{'id': 'thread', 'decision': 'skip', 'reason': 'Verified', 'resolve': True}])
        self.assertFalse(thread['isResolved'])
        self.assertEqual(len(self.fake.writes), 1)


    def test_stopped_batch_resumes_without_consuming_a_round(self):
        first = self.monitor.poll(1, 'session')
        self.monitor.stop(1, 'session', 'user-stopped')
        self.monitor.register(1, 'replacement-session')
        resumed = self.monitor.poll(1, 'replacement-session')
        self.assertEqual((resumed['round'], resumed['items']), (first['round'], first['items']))


    def test_quiet_period_restarts_when_feedback_changes(self):
        self.monitor.config['quietSeconds'] = 2
        base = pf.time.time()
        self.assertEqual(self.monitor.poll(1, 'session', now=base)['status'], 'waiting')
        self.fake.data = snapshot('Another reviewer update')
        self.assertEqual(self.monitor.poll(1, 'session', now=base + 1)['status'], 'waiting')
        self.assertEqual(self.monitor.poll(1, 'session', now=base + 2)['status'], 'waiting')
        self.assertEqual(self.monitor.poll(1, 'session', now=base + 3)['status'], 'batch')

    def test_verified_push_after_interruption_can_resume_the_same_batch(self):
        self.monitor.poll(1, 'session')
        self.monitor.stop(1, 'session', 'user-stopped')
        self.fake.head = 'pushed'
        original_run = pf.run
        def run(argv, *args, **kwargs):
            if argv == ['git', 'rev-parse', 'HEAD']:
                return 'pushed'
            return original_run(argv, *args, **kwargs)
        with patch.object(pf, 'run', side_effect=run):
            state = self.monitor.register(1, 'replacement', pushed_head='pushed')
            self.assertEqual((state['status'], state['rounds']), ('batch', 1))
            report = self.monitor.respond(1, 'replacement', [{'id': 'c1', 'decision': 'fix', 'reason': 'Verified fix'}], 'pushed')
            self.monitor.finish(1, 'replacement', report, 'pushed')
        self.assertEqual(self.monitor.read(1)['head'], 'pushed')


    def test_pushed_fix_can_reply_to_a_now_outdated_thread(self):
        self.fake.data = snapshot('')
        thread = {'id': 'thread', 'isResolved': False, 'isOutdated': False,
            'viewerCanResolve': True, 'comments': {'nodes': [comment()]}}
        self.fake.data['reviewThreads'] = [thread]
        self.monitor.poll(1, 'session')
        thread['isOutdated'] = True
        self.fake.head = 'pushed'
        original_run = pf.run
        def run(argv, *args, **kwargs):
            return 'pushed' if argv == ['git', 'rev-parse', 'HEAD'] else original_run(argv, *args, **kwargs)
        with patch.object(pf, 'run', side_effect=run):
            report = self.monitor.respond(1, 'session', [{'id': 'thread', 'decision': 'fix', 'reason': 'Fixed and tested', 'resolve': True}], 'pushed')
            self.monitor.finish(1, 'session', report, 'pushed')
        self.assertTrue(thread['isResolved'])
        self.assertEqual(self.monitor.read(1)['head'], 'pushed')

    def test_session_end_stops_monitor(self):
        event = {'hook_event_name': 'SessionEnd', 'session_id': 'session', 'cwd': str(self.root)}
        with patch.object(hook, 'Monitor', return_value=self.monitor):
            hook.handle(event)
        self.assertEqual(self.monitor.read(1)['reason'], 'session-ended')


class CollectionTest(unittest.TestCase):
    def test_thread_own_reply_ignored_but_human_followup_and_forged_marker_detected(self):
        data = snapshot('')
        thread = {'id': 't1', 'isResolved': False, 'isOutdated': True, 'viewerCanResolve': True, 'comments': {'nodes': [comment()]}}
        data['reviewThreads'] = [thread]
        original = pf.items_from(data, ['reviewer'])[0]['fingerprint']
        thread['comments']['nodes'].append(comment('own', 'owner', '<!-- hq-pr-feedback:c1 --> replied'))
        self.assertEqual(pf.items_from(data, ['reviewer'])[0]['fingerprint'], original)
        thread['comments']['nodes'].append(comment('human', 'someone', '<!-- hq-pr-feedback:c1 --> disagreement'))
        self.assertNotEqual(pf.items_from(data, ['reviewer'])[0]['fingerprint'], original)
        thread['isResolved'] = True
        self.assertEqual(pf.items_from(data, ['reviewer']), [])

    def test_only_configured_accounts_are_candidates(self):
        data = snapshot()
        data['comments'].append(comment('human', 'someone'))
        self.assertEqual([x['id'] for x in pf.items_from(data, ['REVIEWER'])], ['c1'])

    def test_all_connections_and_long_threads_are_paginated(self):
        github = pf.GitHub('.', 'a/b')
        calls = []
        def graphql(query, **variables):
            calls.append(variables)
            if '$id:ID!' in query:
                return {'node': {'comments': {'nodes': [comment('nested')], 'pageInfo': {'hasNextPage': False}}}}
            field = next(x for x in ('reviewThreads', 'reviews', 'comments') if x + '(first:100,after:' in query)
            if field == 'reviewThreads':
                nodes = [{'id': 't', 'comments': {'nodes': [comment()], 'pageInfo': {'hasNextPage': True, 'endCursor': 'nested'}}}]
                more = False
            else:
                nodes = [{'id': field + str(variables['cursor'])}]
                more = variables['cursor'] is None
            return {'viewer': {'login': 'owner'}, 'repository': {'pullRequest': {field: {'nodes': nodes, 'pageInfo': {'hasNextPage': more, 'endCursor': 'next'}}}}}
        github.graphql = graphql
        data = github.snapshot(1)
        self.assertEqual(len(data['comments']), 2)
        self.assertEqual(len(data['reviews']), 2)
        self.assertEqual(len(data['reviewThreads'][0]['comments']['nodes']), 2)
        self.assertEqual(len(calls), 6)

    def test_non_creation_output_cannot_register_a_monitor(self):
        self.assertFalse(hook.creation_candidate({'tool_name': 'Bash', 'tool_input': {'command': 'gh pr view 1'}}))
        self.assertTrue(hook.creation_candidate({'tool_name': 'mcp__github__create_pull_request', 'tool_input': {}}))


if __name__ == '__main__':
    unittest.main()
