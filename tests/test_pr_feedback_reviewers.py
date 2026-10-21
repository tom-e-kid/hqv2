"""Reviewer wait policies affect completion, never feedback eligibility."""
import copy
import json
import unittest
from unittest.mock import patch

import test_pr_feedback as shared

pf = shared.pf


class ReviewerPolicyTest(unittest.TestCase):
    setUp = shared.MonitorTest.setUp

    def configure(self, reviewers):
        self.config_path.write_text(json.dumps(dict(self.config, reviewers=reviewers)))
        self.monitor = pf.Monitor(self.root)
        self.monitor.github = self.fake

    def mixed(self):
        self.configure(['reviewer', {'login': 'Once[bot]', 'waitAfterPush': False}])
        self.fake.data['reviews'].append({'id': 'once', 'body': '', 'author': {'login': 'once'},
                                         'commit': {'oid': 'head'}, 'state': 'COMMENTED'})

    def push(self, report):
        self.fake.head = 'pushed'
        original = pf.run
        with patch.object(pf, 'run', side_effect=lambda argv, *a, **kw:
                'pushed' if argv == ['git', 'rev-parse', 'HEAD'] else original(argv, *a, **kw)):
            self.monitor.finish(1, 'session', report, pushed_head='pushed')

    def test_mixed_reviewers_batch_then_converge_without_waiting_for_once_again(self):
        self.mixed()
        batch = self.monitor.poll(1, 'session')
        report = self.monitor.respond(1, 'session', [{'id': x['id'], 'decision': 'skip', 'reason': 'Verified'} for x in batch['items']])
        self.push(report)
        self.assertEqual(self.monitor.poll(1, 'session')['status'], 'waiting')
        self.fake.data['reviews'][0]['commit']['oid'] = 'pushed'
        result = self.monitor.poll(1, 'session')
        self.assertEqual(result['reason'], 'converged')
        self.assertTrue(result['reviewersComplete'])
        self.assertEqual(self.monitor.read(1)['rounds'], 1)

    def test_once_reviewer_still_requires_first_submitted_review(self):
        self.configure([{'login': 'reviewer', 'waitAfterPush': False}, {'login': 'once', 'waitAfterPush': False}])
        self.assertEqual(self.monitor.poll(1, 'session')['status'], 'waiting')
        self.assertEqual(self.monitor.poll(1, 'session', now=10**12)['status'], 'batch')
        self.assertFalse(self.monitor.poll(1, 'session').get('reviewersComplete', False))

    def test_string_and_default_object_still_require_current_head(self):
        for reviewer in ('reviewer', {'login': 'reviewer'}):
            with self.subTest(reviewer=reviewer):
                self.configure([reviewer])
                self.fake.data['reviews'][0]['commit']['oid'] = 'old'
                self.assertEqual(self.monitor.poll(1, 'session')['status'], 'waiting')

    def test_draft_or_dismissed_reviews_never_complete_once_policy(self):
        for state in ('PENDING', 'DISMISSED'):
            with self.subTest(state=state):
                self.configure([{'login': 'reviewer', 'waitAfterPush': False}])
                self.fake.data['reviews'][0]['state'] = state
                self.assertEqual(self.monitor.poll(1, 'session')['status'], 'waiting')

    def test_additional_once_feedback_after_push_is_batched(self):
        self.mixed()
        initial = self.monitor.poll(1, 'session')
        report = self.monitor.respond(1, 'session', [{'id': x['id'], 'decision': 'skip', 'reason': 'Verified'} for x in initial['items']])
        self.push(report)
        self.fake.data['reviews'][0]['commit']['oid'] = 'pushed'
        self.fake.data['comments'].append(shared.comment('once-followup', 'once', 'Another problem'))
        self.assertEqual([x['id'] for x in self.monitor.poll(1, 'session')['items']], ['once-followup'])

    def test_policy_does_not_change_item_fingerprints_or_reviewer_followups(self):
        self.fake.data['reviewThreads'] = [{'id': 'thread', 'isResolved': False, 'isOutdated': False,
            'viewerCanResolve': True, 'comments': {'nodes': [shared.comment()]}}]
        before = pf.items_from(self.fake.data, ['reviewer'])
        after = pf.items_from(self.fake.data, [{'login': 'reviewer', 'waitAfterPush': False}])
        self.assertEqual(before, after)
        self.fake.data['reviewThreads'][0]['comments']['nodes'].append(shared.comment('followup', 'reviewer', 'Update'))
        self.assertNotEqual(pf.items_from(self.fake.data, [{'login': 'reviewer'}])[-1]['triggerFingerprint'], after[-1]['triggerFingerprint'])

    def test_once_reviewer_followup_does_not_block_justified_resolve(self):
        self.mixed()
        self.fake.data['comments'] = []
        self.fake.data['reviewThreads'] = [{'id': 'thread', 'isResolved': False, 'isOutdated': False,
            'viewerCanResolve': True, 'comments': {'nodes': [shared.comment(), shared.comment('followup', 'once', 'Details')]}}]
        self.monitor.poll(1, 'session')
        report = self.monitor.respond(1, 'session', [{'id': 'thread', 'decision': 'skip', 'reason': 'Verified', 'resolve': True}])
        self.assertTrue(report[0]['resolved'])

    def test_config_normalizes_logins_and_defaults_to_waiting(self):
        self.configure(['Reviewer[bot]', {'login': 'ONCE', 'waitAfterPush': False}, {'login': 'Other'}])
        self.assertEqual(self.monitor.config['reviewers'], [
            {'login': 'reviewer', 'waitAfterPush': True}, {'login': 'once', 'waitAfterPush': False},
            {'login': 'other', 'waitAfterPush': True}])

    def test_invalid_or_ambiguous_policy_is_rejected(self):
        invalid = [[], {}, [None], [True], [{'login': 1}], [{'login': 'bad[login]'}],
            [{'login': 'reviewer', 'waitAfterPush': 1}], [{'login': 'reviewer', 'waitAfterPush': 'false'}],
            [{'login': 'reviewer', 'waitAfterPush': None}], [{'login': 'reviewer', 'rereview': False}],
            ['Reviewer[bot]', {'login': 'reviewer', 'waitAfterPush': False}], ['reviewer', 'REVIEWER']]
        for reviewers in invalid:
            with self.subTest(reviewers=reviewers), self.assertRaises(pf.FeedbackError):
                self.configure(reviewers)

    def test_reload_policy_preserves_existing_state_and_cap(self):
        state = self.monitor.read(1)
        state.update(rounds=3, processed={'old': 'fingerprint'})
        self.monitor.save(state)
        self.mixed()
        self.assertEqual(self.monitor.read(1), state)
        self.assertEqual(self.monitor.poll(1, 'session')['reason'], 'cap-reached')

    def test_quiet_period_required_even_at_deadline(self):
        self.configure([{'login': 'reviewer', 'waitAfterPush': False}])
        self.monitor.config['quietSeconds'] = 2
        self.fake.data['comments'] = []
        deadline = self.monitor.read(1)['deadline']
        self.assertEqual(self.monitor.poll(1, 'session', now=deadline)['reason'], 'wait-timeout')

    def test_new_ignored_summary_restarts_quiet_period_before_convergence(self):
        self.configure([{'login': 'reviewer', 'waitAfterPush': False}, {'login': 'copilot-pull-request-reviewer'}])
        self.monitor.config['quietSeconds'] = 2
        self.fake.data['comments'] = []
        base = pf.time.time()
        self.assertEqual(self.monitor.poll(1, 'session', now=base)['status'], 'waiting')
        copilot = copy.deepcopy(self.fake.data['reviews'][0])
        copilot.update(id='copilot', body='Summary', author={'login': 'copilot-pull-request-reviewer'})
        self.fake.data['reviews'].append(copilot)
        self.assertEqual(self.monitor.poll(1, 'session', now=base + 2)['status'], 'waiting')
        self.assertEqual(self.monitor.poll(1, 'session', now=base + 4)['reason'], 'converged')
