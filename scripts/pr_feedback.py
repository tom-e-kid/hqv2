#!/usr/bin/env python3
"""Bounded, model-free GitHub PR feedback collection and durable batch bookkeeping."""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time


class FeedbackError(Exception):
    pass


class NotRepository(FeedbackError):
    pass


def run(argv, cwd=None, stdin=None, timeout=45):
    result = subprocess.run(argv, cwd=cwd, input=stdin, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        # Tool errors may include credentials or user content; do not echo raw stderr.
        hint = 'check authentication, permissions and connectivity' if argv[0] == 'gh' else 'check the local Git repository and command preconditions'
        raise FeedbackError(f"{argv[0]} failed (exit {result.returncode}); {hint}")
    return result.stdout.strip()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def login(value):
    return re.sub(r'\[bot\]$', '', value.lower())


def load_config(root):
    path = root / '.hq/v2/pr-feedback.json'
    if not path.exists():
        return None
    config = json.loads(path.read_text())
    if not isinstance(config, dict) or type(config.get('enabled')) is not bool:
        raise FeedbackError('pr-feedback.json: enabled must be boolean')
    if not config['enabled']:
        return None
    if type(config.get('version')) is not int or config['version'] != 1:
        raise FeedbackError('pr-feedback.json: version must be 1')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', config.get('repository', '')):
        raise FeedbackError('pr-feedback.json: repository must be owner/name')
    reviewers = config.get('reviewers')
    if not isinstance(reviewers, list) or not reviewers or any(not isinstance(x, str) or not re.fullmatch(r'[A-Za-z0-9_-]+(?:\[bot\])?', x) for x in reviewers):
        raise FeedbackError('pr-feedback.json: reviewers must be a nonempty list of exact account logins')
    ignored = config.setdefault('ignoreReviewBodies', ['copilot-pull-request-reviewer'])
    if not isinstance(ignored, list) or any(not isinstance(x, str) or not re.fullmatch(r'[A-Za-z0-9_-]+(?:\[bot\])?', x) for x in ignored):
        raise FeedbackError('pr-feedback.json: ignoreReviewBodies must be a list of account logins')
    for key, default, low, high in [('maxRounds', 3, 1, 3), ('quietSeconds', 120, 0, 300), ('waitSeconds', 600, 1, 600), ('pollSeconds', 30, 1, 120)]:
        value = config.setdefault(key, default)
        if type(value) is not int or not low <= value <= high:
            raise FeedbackError(f'pr-feedback.json: invalid {key}')
    if config['quietSeconds'] >= config['waitSeconds']:
        raise FeedbackError('pr-feedback.json: quietSeconds must be less than waitSeconds')
    actions = config.get('actions', {})
    if not isinstance(actions, dict) or any(k not in ('fix', 'push', 'reply', 'resolve') or type(v) is not bool for k, v in actions.items()):
        raise FeedbackError('pr-feedback.json: invalid actions')
    config['actions'] = {key: actions.get(key, False) for key in ('fix', 'push', 'reply', 'resolve')}
    return config


class GitHub:
    def __init__(self, root, repository):
        self.root, self.repository = root, repository
        self.owner, self.name = repository.split('/')
        self.deadline = None
        self.wall_deadline = None

    def api(self, endpoint, method='GET', payload=None):
        argv = ['gh', 'api', '--hostname', 'github.com', endpoint, '--method', method]
        if payload is not None:
            argv += ['--input', '-']
        remaining = 45 if self.deadline is None else min(45, self.deadline - time.monotonic())
        if self.wall_deadline is not None:
            remaining = min(remaining, self.wall_deadline - time.time())
        if remaining <= 0:
            raise FeedbackError('GitHub read deadline exceeded')
        return json.loads(run(argv, self.root, json.dumps(payload) if payload is not None else None, timeout=remaining))

    def graphql(self, query, **variables):
        data = self.api('graphql', 'POST', {'query': query, 'variables': variables})
        if data.get('errors'):
            raise FeedbackError('GitHub GraphQL returned errors; feedback has not been verified')
        return data['data']

    def pr(self, number):
        pr = self.api(f'repos/{self.repository}/pulls/{number}')
        return {'number': number, 'url': pr['html_url'], 'head': pr['head']['sha'],
                'branch': pr['head']['ref'], 'repository': pr['head']['repo']['full_name'] if pr['head']['repo'] else None,
                'open': pr['state'] == 'open'}

    def snapshot(self, number):
        """Page every connection, including comments inside long review threads."""
        collections = {}
        selections = {
            'comments': 'id databaseId body updatedAt url author { login }',
            'reviews': 'id body submittedAt state url commit { oid } author { login }',
            'reviewThreads': 'id isResolved isOutdated viewerCanResolve comments(first:100) { nodes { id databaseId body updatedAt url authorAssociation author { login } } pageInfo { hasNextPage endCursor } }',
        }
        for field, selection in selections.items():
            cursor = None
            nodes = []
            while True:
                query = '''query($owner:String!,$name:String!,$number:Int!,$cursor:String) {
                  viewer { login } repository(owner:$owner,name:$name) { pullRequest(number:$number) {
                    FIELD(first:100,after:$cursor) { nodes { SELECTION } pageInfo { hasNextPage endCursor } }
                  } }
                }'''.replace('FIELD', field).replace('SELECTION', selection)
                data = self.graphql(query, owner=self.owner, name=self.name, number=number, cursor=cursor)
                collections['viewer'] = data['viewer']['login']
                connection = data['repository']['pullRequest'][field]
                nodes.extend(connection['nodes'])
                if not connection['pageInfo']['hasNextPage']:
                    break
                cursor = connection['pageInfo']['endCursor']
            collections[field] = nodes
        for thread in collections['reviewThreads']:
            connection = thread['comments']
            while connection['pageInfo']['hasNextPage']:
                connection = self.graphql('''query($id:ID!,$cursor:String) {
                  node(id:$id) { ... on PullRequestReviewThread { comments(first:100,after:$cursor) {
                    nodes { id databaseId body updatedAt url authorAssociation author { login } } pageInfo { hasNextPage endCursor }
                  } } }
                }''', id=thread['id'], cursor=connection['pageInfo']['endCursor'])['node']['comments']
                thread['comments']['nodes'].extend(connection['nodes'])
        return collections


def items_from(snapshot, reviewers, ignore_review_bodies=('copilot-pull-request-reviewer',)):
    allowed = {login(x) for x in reviewers}
    ignored = {login(x) for x in ignore_review_bodies}
    items = []
    for kind in ('comments', 'reviews', 'reviewThreads'):
        for node in snapshot[kind]:
            if kind == 'reviewThreads':
                comments = node['comments']['nodes']
                if node['isResolved'] or not comments or login((comments[0].get('author') or {}).get('login', '')) not in allowed:
                    continue
                # All bodies remain untrusted input, including collaborator replies.
                content = [c for c in comments if not ((c.get('author') or {}).get('login') == snapshot.get('viewer') and '<!-- hq-pr-feedback:' in c['body'])]
                item = {'id': node['id'], 'kind': 'thread', 'url': comments[0]['url'], 'comments': content,
                        'replyTo': comments[0]['databaseId'], 'canResolve': node['viewerCanResolve'], 'outdated': node['isOutdated']}
            else:
                author = login((node.get('author') or {}).get('login', ''))
                if not node['body'].strip() or author not in allowed or (kind == 'reviews' and author in ignored):
                    continue
                item = dict(node, kind=kind)
            # A pushed fix can change diff placement and permission metadata while
            # the actual discussion stays unchanged. Keep those out of identity.
            item['fingerprint'] = digest({key: value for key, value in item.items() if key not in ('outdated', 'canResolve')})
            if kind == 'reviewThreads':
                trigger = [c for c in content if login((c.get('author') or {}).get('login', '')) in allowed
                           or c.get('authorAssociation') in ('OWNER', 'MEMBER', 'COLLABORATOR')]
                item['triggerFingerprint'] = digest(trigger)
            item['untrustedContext'] = True
            items.append(item)
    return items


class Monitor:
    def __init__(self, cwd):
        try:
            self.root = Path(run(['git', 'rev-parse', '--show-toplevel'], cwd))
        except FeedbackError:
            raise NotRepository('Not a Git working tree') from None
        self.config = load_config(self.root)
        self.store = None
        if self.config:
            common = Path(run(['git', 'rev-parse', '--git-common-dir'], self.root))
            if not common.is_absolute():
                common = self.root / common
            self.store = common / 'hq-pr-feedback' / digest(self.config['repository'])[:16]
            self.github = GitHub(self.root, self.config['repository'])

    @contextmanager
    def lock(self, key, *, required=True):
        self.store.mkdir(parents=True, exist_ok=True)
        with (self.store / f'{key}.lock').open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                if required:
                    raise FeedbackError('PR monitor is busy in another process') from None
                yield False
                return
            yield True

    def path(self, number):
        return self.store / f'{number}.json'

    def read(self, number):
        return json.loads(self.path(number).read_text())

    def save(self, state):
        path = self.path(state['number'])
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(path)

    def session_path(self, session):
        return self.store / f'session-{digest(session)}.json'

    def current_branch(self):
        branch = run(['git', 'branch', '--show-current'], self.root)
        if not branch:
            raise FeedbackError('Detached HEAD; check out the PR head branch before registering or processing feedback')
        return branch

    def check_pr(self, number):
        remote = run(['git', 'remote', 'get-url', 'origin'], self.root)
        match = re.fullmatch(r'(?:git@github\.com:|https://github\.com/|ssh://git@github\.com/)([^/]+/[^/]+?)(?:\.git)?/?', remote)
        if not match or match[1].lower() != self.config['repository'].lower():
            raise FeedbackError('origin must identify the configured github.com repository')
        pr = self.github.pr(number)
        if not pr['open']:
            raise FeedbackError('PR is closed or merged')
        if (pr['repository'] or '').lower() != self.config['repository'].lower() or pr['branch'] != self.current_branch():
            raise FeedbackError('PR head is not the current repository and branch (fork heads are not supported)')
        return pr

    def register(self, number, session, pushed_head=None):
        with self.lock('session-' + digest(session)):
            binding = self.session_path(session)
            if binding.exists():
                previous = json.loads(binding.read_text())['number']
                if previous != number and self.path(previous).exists():
                    previous_state = self.read(previous)
                    if previous_state['session'] == session and previous_state['status'] != 'ended':
                        raise FeedbackError(f'Session already monitors PR #{previous}; stop it explicitly before registering another PR')
            return self._register(number, session, pushed_head)

    def _register(self, number, session, pushed_head=None):
        with self.lock(number):
            resumed = False
            pr = self.check_pr(number)
            verified_push = bool(pushed_head and self.config['actions']['push'] and pr['head'] == pushed_head
                                 and run(['git', 'rev-parse', 'HEAD'], self.root) == pushed_head)
            if pushed_head and not verified_push:
                raise FeedbackError('Resume pushed head must match local HEAD and PR head, with push permitted')
            if self.path(number).exists():
                state = self.read(number)
                if state['status'] != 'ended' and state['session'] != session:
                    raise FeedbackError('PR already owned by another session; stop it before resuming here')
                if state['status'] != 'ended' and state['worktree'] != str(self.root):
                    raise FeedbackError('PR already owned by another worktree; stop it before resuming here')
                if state['status'] != 'ended' and state['head'] != pr['head'] and not verified_push:
                    raise FeedbackError('Unexpected remote head change; inspect before restarting')
                with self.lock(f'{number}-wait', required=False) as available:
                    if available and self.unobserved_expiry(state):
                        self.mark_interrupted(state)
                        resumed = True
                state['session'] = session
                state['worktree'] = str(self.root)
                if state['status'] == 'ended':
                    if state.get('batch'):
                        if state['head'] != pr['head'] and not verified_push:
                            raise FeedbackError('Interrupted batch head changed; reconcile the saved batch before resuming')
                        state.update(status='batch', notified=False)
                        state.pop('dispatchedRound', None)
                    else:
                        state.update(status='waiting', head=pr['head'], deadline=time.time() + self.config['waitSeconds'], lastChange=time.time(), notified=False)
            else:
                state = dict(pr, status='waiting', rounds=0, processed={}, batch=None, observed=None,
                             session=session, worktree=str(self.root), deadline=time.time() + self.config['waitSeconds'], lastChange=time.time())
            self.save(state)
            self.session_path(session).write_text(json.dumps({'number': number}))
            return dict(state, resumedAfterInterruption=True) if resumed else state

    def items(self, snapshot):
        return items_from(snapshot, self.config['reviewers'], self.config['ignoreReviewBodies'])

    def refresh(self, number, session, pushed_head=None):
        """Reconcile an interrupted batch without consuming or resetting a round."""
        with self.lock(number):
            state = self.owned(number, session)
            if state['status'] != 'batch':
                raise FeedbackError('No active batch; register a stopped batch before refreshing')
            pr = self.check_pr(number)
            if pushed_head:
                if not self.config['actions']['push'] or pr['head'] != pushed_head or run(['git', 'rev-parse', 'HEAD'], self.root) != pushed_head:
                    raise FeedbackError('Refresh pushed head must match local HEAD and PR head, with push permitted')
            elif pr['head'] != state['head']:
                raise FeedbackError('Head changed; supply the verified pushed head')
            snapshot = self.github.snapshot(number)
            if self.github.pr(number)['head'] != pr['head']:
                raise FeedbackError('Head changed while refreshing feedback')
            current = {x['id']: x for x in self.items(snapshot)}
            resolved = {x['id'] for x in snapshot['reviewThreads'] if x['isResolved']}
            batch = []
            for old in state['batch']:
                key = digest([old['id'], old['fingerprint'], state['rounds']])
                operation = state.get('operations', {}).get(key, {})
                # Keep completed operations available to retry/finish. Legacy
                # thread operations lack intent, so require a confirmed Resolve.
                resolve_requested = operation.get('resolveRequested', old['kind'] == 'thread')
                if operation.get('replyUrl') and (not resolve_requested or operation.get('resolved')):
                    batch.append(old)
                    continue
                if old['id'] in current:
                    latest = current[old['id']]
                    if old.get('requiresReevaluation') or old.get('superseded') or old['fingerprint'] != latest['fingerprint']:
                        latest['requiresReevaluation'] = True
                    batch.append(latest)
                else:
                    batch.append(dict(old, superseded='resolved' if old['id'] in resolved else 'no-longer-present'))
            if batch != state['batch']:
                state.setdefault('batchRefreshes', []).append({'round': state['rounds'], 'items': state['batch']})
            state['batch'] = batch
            self.save(state)
            return state

    def owned(self, number, session):
        state = self.read(number)
        if state['session'] != session or state['worktree'] != str(self.root):
            raise FeedbackError('Monitor belongs to another session or worktree')
        return state

    @staticmethod
    def unobserved_expiry(state):
        return (state['status'] == 'waiting' and time.time() >= state['deadline']
                and (state.get('lastPolledAt') or 0) < state['deadline'])

    @staticmethod
    def mark_interrupted(state):
        state['lastInterruption'] = {'detectedAt': time.time(), 'deadline': state['deadline'],
                                     'lastPolledAt': state.get('lastPolledAt')}
        state.update(status='ended', reason='wait-interrupted', notified=False)

    def status(self, number, session):
        """Diagnose abandoned waits without changing saved state or contacting GitHub."""
        with self.lock(number):
            state = self.owned(number, session)
            with self.lock(f'{number}-wait', required=False) as available:
                return dict(state, waitActive=not available,
                            interruptionSuspected=available and self.unobserved_expiry(state))

    def begin_wait(self, number, session):
        """Called only while holding the separate, process-lifetime wait lock."""
        with self.lock(number):
            state = self.owned(number, session)
            if self.unobserved_expiry(state):
                self.mark_interrupted(state)
                self.save(state)
            return state

    def poll(self, number, session, now=None):
        with self.lock(number):
            state = self.owned(number, session)
            if state['status'] == 'ended':
                return {'status': 'ended', 'reason': state.get('reason')}
            if state['status'] == 'batch':
                return {'status': 'batch', 'round': state['rounds'], 'items': state['batch']}
            pr = self.check_pr(number)
            if pr['head'] != state['head']:
                raise FeedbackError('Unexpected remote head change; no feedback processed')
            snapshot = self.github.snapshot(number)
            # Guard against a push during paginated reads.
            if self.github.pr(number)['head'] != state['head']:
                raise FeedbackError('Head changed while collecting feedback')
            now = time.time() if now is None else now
            state['lastPolledAt'] = now
            items = self.items(snapshot)
            resolved = {x['id'] for x in snapshot['reviewThreads'] if x['isResolved']}
            for reopened in set(state.get('resolvedThreads', [])) - resolved:
                state['processed'].pop(reopened, None)
            state['resolvedThreads'] = sorted(resolved)
            pending = [x for x in items if state['processed'].get(x['id']) != x.get('triggerFingerprint', x['fingerprint'])]
            observed = digest([(x['id'], x.get('triggerFingerprint', x['fingerprint'])) for x in pending])
            if state['observed'] != observed:
                state.update(observed=observed, lastChange=now)
            quiet = now - state['lastChange'] >= self.config['quietSeconds']
            # A submitted review for this head establishes completion only for its author.
            completed = {login((x.get('author') or {}).get('login', '')) for x in snapshot['reviews']
                         if (x.get('commit') or {}).get('oid') == state['head'] and x['state'] in ('COMMENTED', 'APPROVED', 'CHANGES_REQUESTED')}
            all_done = {login(x) for x in self.config['reviewers']} <= completed
            expired = now >= state['deadline']
            if pending and quiet and (all_done or expired):
                if state['rounds'] >= self.config['maxRounds']:
                    state.update(status='ended', reason='cap-reached', remaining=pending)
                else:
                    state.update(status='batch', rounds=state['rounds'] + 1, batch=pending)
            elif expired or (all_done and quiet and not pending):
                state.update(status='ended', reason='converged' if all_done and quiet and not pending else 'wait-timeout', remaining=pending)
            self.save(state)
            return {'status': state['status'], 'round': state['rounds'], 'reason': state.get('reason'),
                    'items': state.get('batch') if state['status'] == 'batch' else state.get('remaining', []),
                    'reviewersComplete': all_done, 'deadline': state['deadline']}

    def finish(self, number, session, report, pushed_head=None):
        with self.lock(number):
            state = self.owned(number, session)
            if state['status'] != 'batch':
                raise FeedbackError('No active batch')
            if not isinstance(report, list) or {x.get('id') for x in report} != {x['id'] for x in state['batch']} or len(report) != len(state['batch']):
                raise FeedbackError('Report must cover each batch item exactly once')
            for item in report:
                source = next(x for x in state['batch'] if x['id'] == item['id'])
                if source.get('superseded'):
                    if item.get('decision') != 'superseded' or item.get('reason') != source['superseded'] or item.get('resolve'):
                        raise FeedbackError('Superseded item must record the refresh result without Resolve')
                    continue
                if source.get('requiresReevaluation') and item.get('fingerprint') != source['fingerprint']:
                    raise FeedbackError('Refreshed item requires the latest fingerprint after re-evaluation')
                if item.get('decision') not in ('fix', 'defer', 'skip', 'hold') or not isinstance(item.get('reason'), str) or not item['reason'].strip():
                    raise FeedbackError('Each report item needs decision and reason')
                if not item.get('replyUrl'):
                    raise FeedbackError('Each item needs a verified reply URL; retry incomplete operations or stop')
                operation = state.get('operations', {}).get(digest([source['id'], source['fingerprint'], state['rounds']]), {})
                if (operation.get('replyUrl'), operation.get('decision'), operation.get('reason')) != (item['replyUrl'], item['decision'], item['reason']):
                    raise FeedbackError('Reply result must match a recorded respond operation')
                if item.get('resolve') and not operation.get('resolved'):
                    raise FeedbackError('Resolve is not confirmed; retry respond before finishing')
            pr = self.check_pr(number)
            if pushed_head:
                if pr['head'] != pushed_head or run(['git', 'rev-parse', 'HEAD'], self.root) != pushed_head:
                    raise FeedbackError('pushed head must match local HEAD and PR head')
            elif pr['head'] != state['head']:
                raise FeedbackError('Head changed; supply the verified pushed head')
            if any(x.get('superseded') for x in state['batch']):
                current = {x['id'] for x in self.items(self.github.snapshot(number))}
                if any(x.get('superseded') and x['id'] in current for x in state['batch']):
                    raise FeedbackError('Superseded feedback reappeared; refresh and re-evaluate')
                if self.github.pr(number)['head'] != pr['head']:
                    raise FeedbackError('Head changed while verifying superseded feedback')
            state.setdefault('reports', []).append({'round': state['rounds'], 'items': report, 'head': pr['head']})
            state['resolvedThreads'] = sorted(set(state.get('resolvedThreads', []))
                                             | {x['id'] for x in report if x.get('resolved')}
                                             | {x['id'] for x in state['batch'] if x.get('superseded') == 'resolved'})
            state['processed'].update({x['id']: x.get('triggerFingerprint', x['fingerprint']) for x in state['batch'] if not x.get('superseded')})
            state.update(status='waiting', head=pr['head'], batch=None, observed=None, deadline=time.time() + self.config['waitSeconds'], lastChange=time.time())
            self.save(state)
            return state

    def respond(self, number, session, report, pushed_head=None):
        """Reply idempotently, persist each successful step, then resolve if justified."""
        if not self.config['actions']['reply']:
            raise FeedbackError('Reply is disabled in actions')
        with self.lock(number):
            state = self.owned(number, session)
            if state['status'] != 'batch':
                raise FeedbackError('No active batch')
            batch = {x['id']: x for x in state['batch']}
            if not isinstance(report, list) or len(report) != len(batch) or {x.get('id') for x in report} != set(batch):
                raise FeedbackError('Report must cover each batch item exactly once')
            for entry in report:
                source = batch[entry['id']]
                if source.get('superseded'):
                    if entry.get('decision') != 'superseded' or entry.get('reason') != source['superseded'] or entry.get('resolve'):
                        raise FeedbackError('Superseded item must record the refresh result without Resolve')
                    continue
                if source.get('requiresReevaluation') and entry.get('fingerprint') != source['fingerprint']:
                    raise FeedbackError('Refreshed item requires the latest fingerprint after re-evaluation')
                if entry.get('decision') not in ('fix', 'defer', 'skip', 'hold') or not isinstance(entry.get('reason'), str) or not entry['reason'].strip():
                    raise FeedbackError('Each report item needs decision and reason')
                if entry.get('resolve') and (entry['decision'] not in ('fix', 'skip') or not self.config['actions']['resolve']):
                    raise FeedbackError('Resolve requires fix/skip and actions.resolve')
                if entry['decision'] == 'fix' and (not pushed_head or not self.config['actions']['fix'] or not self.config['actions']['push']):
                    raise FeedbackError('A fix reply requires permitted fix/push and --pushed-head')
            pr = self.check_pr(number)
            if pushed_head:
                if pr['head'] != pushed_head or run(['git', 'rev-parse', 'HEAD'], self.root) != pushed_head:
                    raise FeedbackError('pushed head must match local HEAD and PR head')
            elif pr['head'] != state['head']:
                raise FeedbackError('Head changed before reply')
            snapshot = self.github.snapshot(number)
            viewer = snapshot['viewer']
            comments = snapshot['comments'] + [c for t in snapshot['reviewThreads'] for c in t['comments']['nodes']]
            current = {x['id']: x for x in self.items(snapshot)}
            threads = {t['id']: t for t in snapshot['reviewThreads']}
            # Check the whole plan before its first write, including changed human replies.
            for entry in report:
                item = batch[entry['id']]
                if item.get('superseded'):
                    if item['id'] in current:
                        raise FeedbackError('Superseded feedback reappeared; refresh and re-evaluate')
                    continue
                key = digest([item['id'], item['fingerprint'], state['rounds']])
                already_replied = not entry.get('resolve') and state.get('operations', {}).get(key, {}).get('replyUrl')
                already_resolved = (entry.get('resolve') and threads.get(entry['id'], {}).get('isResolved')
                                    and state.get('operations', {}).get(key, {}).get('replyUrl'))
                if not (already_replied or already_resolved) and (entry['id'] not in current or current[entry['id']]['fingerprint'] != item['fingerprint']):
                    raise FeedbackError('Feedback changed or was resolved; use refresh and re-evaluate before replying')
                if entry.get('resolve'):
                    thread = threads.get(entry['id'])
                    if not thread or (not thread['isResolved'] and not thread['viewerCanResolve']):
                        raise FeedbackError('Item is not a resolvable review thread')
                    if not thread['isResolved']:
                        authors = {login((c.get('author') or {}).get('login', '')) for c in thread['comments']['nodes']}
                        if authors - {login(viewer), *(login(x) for x in self.config['reviewers'])}:
                            raise FeedbackError('Human/unknown follow-up prevents automatic Resolve')
            operations = state.setdefault('operations', {})
            for entry in report:
                item = batch[entry['id']]
                if item.get('superseded'):
                    continue
                key = digest([item['id'], item['fingerprint'], state['rounds']])
                marker = f'<!-- hq-pr-feedback:{key} -->'
                operation = operations.setdefault(key, {})
                if operation.get('decision') and (operation['decision'], operation['reason']) != (entry['decision'], entry['reason']):
                    raise FeedbackError('A reply already exists for a different decision; inspect it before editing')
                if entry.get('resolve'):
                    operation['resolveRequested'] = True
                    self.save(state)
                existing = next((c for c in comments if (c.get('author') or {}).get('login') == viewer and marker in c['body']), None)
                if existing:
                    operation['replyUrl'] = existing['url']
                if not operation.get('replyUrl'):
                    if self.github.pr(number)['head'] != pr['head']:
                        raise FeedbackError('Head changed before reply')
                    # Persist intent before sending. On ambiguous failure the next call looks up the marker.
                    operation.update(decision=entry['decision'], reason=entry['reason'], resolveRequested=bool(entry.get('resolve')))
                    self.save(state)
                    body = f'{marker}\n{entry["decision"]}: {entry["reason"]}\n\n対象: {item["url"]}'
                    if pushed_head and entry['decision'] == 'fix':
                        body += f'\n反映コミット: {pushed_head}'
                    endpoint = (f'repos/{self.config["repository"]}/pulls/{number}/comments/{item["replyTo"]}/replies'
                                if item['kind'] == 'thread' else f'repos/{self.config["repository"]}/issues/{number}/comments')
                    response = self.github.api(endpoint, 'POST', {'body': body})
                    operation['replyUrl'] = response['html_url']
                    self.save(state)
                entry['replyUrl'] = operation['replyUrl']
                if entry.get('resolve') and threads[item['id']]['isResolved']:
                    operation['resolved'] = True
                    self.save(state)
                if entry.get('resolve') and not operation.get('resolved'):
                    # Recheck head immediately before mutating thread state.
                    if self.github.pr(number)['head'] != pr['head']:
                        raise FeedbackError('Head changed before Resolve')
                    fresh = self.github.snapshot(number)
                    latest = {x['id']: x for x in self.items(fresh)}
                    if item['id'] not in latest or latest[item['id']]['fingerprint'] != item['fingerprint']:
                        raise FeedbackError('Thread changed before Resolve; inspect it before retrying')
                    self.github.graphql('mutation($id:ID!) { resolveReviewThread(input:{threadId:$id}) { thread { isResolved } } }', id=item['id'])
                    operation['resolved'] = True
                    self.save(state)
                entry['resolved'] = operation.get('resolved', False)
                self.save(state)
            return report

    def stop(self, number, session, reason):
        with self.lock(number):
            state = self.owned(number, session)
            state.update(status='ended', reason=reason)
            self.save(state)
            return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['register', 'poll', 'status', 'refresh', 'respond', 'finish', 'stop'])
    parser.add_argument('--repo', default='.')
    parser.add_argument('--pr', type=int, required=True)
    parser.add_argument('--session', required=True)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--pushed-head')
    parser.add_argument('--reason', default='user-stopped')
    args = parser.parse_args()
    monitor = Monitor(args.repo)
    if not monitor.config:
        print(json.dumps({'status': 'disabled'}))
        return
    if args.pr < 1:
        raise FeedbackError('Invalid PR number')
    if args.command == 'register':
        result = monitor.register(args.pr, args.session, args.pushed_head)
    elif args.command == 'poll':
        result = monitor.poll(args.pr, args.session)
    elif args.command == 'status':
        result = monitor.status(args.pr, args.session)
    elif args.command == 'stop':
        result = monitor.stop(args.pr, args.session, args.reason)
    elif args.command == 'refresh':
        result = monitor.refresh(args.pr, args.session, args.pushed_head)
    else:
        if not args.report:
            raise FeedbackError(f'{args.command} requires --report')
        report = json.loads(args.report.read_text())
        if args.command == 'respond':
            result = monitor.respond(args.pr, args.session, report, args.pushed_head)
            args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
        else:
            result = monitor.finish(args.pr, args.session, report, args.pushed_head)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (FeedbackError, OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
        print(f'HQ pr-feedback: {error}', file=sys.stderr)
        sys.exit(2)
