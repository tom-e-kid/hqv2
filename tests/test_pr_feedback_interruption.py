"""Interrupted waits must be visible without stealing a live monitor."""
import json
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import test_pr_feedback as shared

pf, hook = shared.pf, shared.hook


class InterruptionTest(unittest.TestCase):
    setUp = shared.MonitorTest.setUp

    def expire(self):
        state = self.monitor.read(1)
        state.update(deadline=pf.time.time() - 10, rounds=2, processed={'old': 'fingerprint'})
        self.monitor.save(state)
        return state

    def event(self):
        return {'hook_event_name': 'Stop', 'session_id': 'session', 'cwd': str(self.root)}

    def test_status_detects_abandoned_legacy_wait_without_mutating_it(self):
        old = self.expire()
        status = self.monitor.status(1, 'session')
        self.assertTrue(status['interruptionSuspected'])
        self.assertFalse(status['waitActive'])
        self.assertEqual(self.monitor.read(1), old)

    def test_live_wait_is_not_interrupted_or_restarted_even_after_deadline(self):
        old = self.expire()
        with self.monitor.lock('1-wait'):
            self.assertTrue(self.monitor.status(1, 'session')['waitActive'])
            self.assertFalse(self.monitor.status(1, 'session')['interruptionSuspected'])
            self.monitor.register(1, 'session')
            with patch.object(hook, 'Monitor', return_value=self.monitor):
                self.assertIsNone(hook.handle(self.event()))
        self.assertEqual(self.monitor.read(1), old)

    def test_next_hook_reports_interruption_once_without_fetching(self):
        self.expire()
        with patch.object(hook, 'Monitor', return_value=self.monitor), patch.object(self.fake, 'snapshot') as fetch:
            result = hook.handle(self.event())
            self.assertIn('wait-interrupted', result['reason'])
            self.assertIsNone(hook.handle(self.event()))
            fetch.assert_not_called()
        self.assertEqual(self.monitor.read(1)['rounds'], 2)

    def test_explicit_registration_resumes_and_preserves_history(self):
        old = self.expire()
        state = self.monitor.register(1, 'session')
        self.assertTrue(state['resumedAfterInterruption'])
        self.assertGreater(state['deadline'], pf.time.time())
        self.assertEqual((state['rounds'], state['processed']), (2, old['processed']))
        self.assertEqual(state['lastInterruption']['deadline'], old['deadline'])
        self.assertNotIn('resumedAfterInterruption', self.monitor.register(1, 'session'))

    def test_successful_poll_records_observation_but_failure_does_not(self):
        self.fake.data = shared.snapshot('', complete=False)
        self.monitor.poll(1, 'session')
        observed = self.monitor.read(1)['lastPolledAt']
        self.fake.snapshot = Mock(side_effect=pf.FeedbackError('offline'))
        with self.assertRaises(pf.FeedbackError):
            self.monitor.poll(1, 'session')
        self.assertEqual(self.monitor.read(1)['lastPolledAt'], observed)

    def test_poll_after_deadline_can_still_collect_feedback(self):
        self.expire()
        result = self.monitor.poll(1, 'session')
        self.assertEqual(result['status'], 'batch')
        self.assertFalse(self.monitor.status(1, 'session')['interruptionSuspected'])

    def test_status_cli_returns_diagnostic(self):
        self.expire()
        with patch.object(pf, 'Monitor', return_value=self.monitor), patch.object(sys, 'argv',
                ['pr_feedback.py', 'status', '--pr', '1', '--session', 'session']), patch('builtins.print') as output:
            pf.main()
        self.assertTrue(json.loads(output.call_args.args[0])['interruptionSuspected'])

    def test_process_death_releases_wait_lock_and_exposes_saved_wait(self):
        old = self.expire()
        child = subprocess.Popen([sys.executable, '-c',
            'import fcntl,sys; f=open(sys.argv[1], "a"); '
            'fcntl.flock(f, fcntl.LOCK_EX); print("locked", flush=True); sys.stdin.read()',
            str(self.monitor.store / '1-wait.lock')], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'locked')
            self.assertFalse(self.monitor.status(1, 'session')['interruptionSuspected'])
            child.kill()
            child.wait(timeout=5)
            self.assertTrue(self.monitor.status(1, 'session')['interruptionSuspected'])
            self.assertEqual(self.monitor.read(1), old)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)

    def test_normal_timeout_and_active_batch_are_not_interruption(self):
        self.fake.data = shared.snapshot('', complete=False)
        self.monitor.poll(1, 'session', now=10**12)
        self.assertEqual(self.monitor.status(1, 'session')['reason'], 'wait-timeout')
        self.assertFalse(self.monitor.status(1, 'session')['interruptionSuspected'])
        self.monitor.register(1, 'session')
        self.fake.data = shared.snapshot()
        self.monitor.poll(1, 'session')
        self.assertFalse(self.monitor.status(1, 'session')['interruptionSuspected'])

    def test_wall_clock_limits_api_call_after_monotonic_pauses(self):
        github = pf.GitHub(self.root, 'a/b')
        github.deadline = pf.time.monotonic() + 100
        github.wall_deadline = pf.time.time() - 1
        with patch.object(pf, 'run') as run:
            with self.assertRaises(pf.FeedbackError):
                github.api('example')
        run.assert_not_called()

    def test_hook_uses_wall_clock_budget_after_sleep(self):
        self.fake.data = shared.snapshot('', complete=False)
        base = pf.time.time()
        current = [base]

        def sleep(_):
            current[0] += 1000  # Simulate sleep while monotonic does not advance.

        with patch.object(hook, 'Monitor', return_value=self.monitor), patch.object(hook.time, 'time', side_effect=lambda: current[0]), \
                patch.object(hook, 'prevent_idle_sleep'), patch.object(self.fake, 'snapshot', wraps=self.fake.snapshot) as fetch:
            result = hook.handle(self.event(), sleep=sleep, monotonic=lambda: 0)
        self.assertIn('wait-timeout', result['reason'])
        self.assertEqual(fetch.call_count, 1)


class SleepGuardTest(unittest.TestCase):
    def test_darwin_guard_is_pid_bound_and_reaped_on_success_and_error(self):
        for fail in (False, True):
            process = Mock()
            process.poll.return_value = None
            with self.subTest(fail=fail), patch.object(hook.sys, 'platform', 'darwin'), \
                    patch.object(hook.subprocess, 'Popen', return_value=process) as start:
                try:
                    with hook.prevent_idle_sleep(True):
                        if fail:
                            raise ValueError('test')
                except ValueError:
                    pass
                self.assertEqual(start.call_args.args[0], ['/usr/bin/caffeinate', '-i', '-w', str(hook.os.getpid())])
                process.terminate.assert_called_once()
                process.wait.assert_called_once()

    def test_other_platform_and_nonwaiting_state_do_not_spawn(self):
        with patch.object(hook.subprocess, 'Popen') as start:
            with patch.object(hook.sys, 'platform', 'linux'), hook.prevent_idle_sleep(True):
                pass
            with patch.object(hook.sys, 'platform', 'darwin'), hook.prevent_idle_sleep(False):
                pass
        start.assert_not_called()

    def test_guard_failure_warns_without_aborting_monitor(self):
        with patch.object(hook.sys, 'platform', 'darwin'), patch.object(hook.subprocess, 'Popen', side_effect=OSError), \
                patch.object(hook.sys, 'stderr') as stderr:
            with hook.prevent_idle_sleep(True):
                pass
        self.assertIn('idle sleep prevention failed', ''.join(c.args[0] for c in stderr.write.call_args_list))

    def test_child_is_killed_and_reaped_if_cleanup_times_out(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('caffeinate', 1), 0]
        with patch.object(hook.sys, 'platform', 'darwin'), patch.object(hook.subprocess, 'Popen', return_value=process):
            with hook.prevent_idle_sleep(True):
                pass
        process.kill.assert_called_once()
        self.assertEqual(process.wait.call_count, 2)
