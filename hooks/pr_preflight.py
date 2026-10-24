#!/usr/bin/env python3
"""Pause PR creation for a work-record review; never decide whether work is finished."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import sys
import tempfile
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import wip
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pr_event import tool_arguments, tool_command
from ssot_check import remote_repositories

OID = re.compile(r'[0-9a-f]{40}|[0-9a-f]{64}')
REPOSITORY = re.compile(r'(?:(?P<host>[\w.-]+)/)?(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)')


class Unchecked(Exception):
    """No safe association between the pending call and its work records is available."""


def target(repository, base, head):
    match = REPOSITORY.fullmatch(repository) if isinstance(repository, str) else None
    if not match or not all(isinstance(x, str) and x and not x.startswith('-') for x in (base, head)):
        raise Unchecked('Specify repository, base and head explicitly; defaults are not inferred.')
    # Fork heads need a distinct repository identity, not just a commit in this clone.
    if ':' in head:
        raise Unchecked('Fork-qualified heads are not supported by this preflight; use an explicit same-repository head.')
    return {'host': (match['host'] or 'github.com').lower(),
            'repository': f"{match['owner']}/{match['repo']}".lower(), 'base': base, 'head': head}


def shell_tokens(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=';&|<>()')
    lexer.whitespace_split = True
    return list(lexer)


def creation_candidate(event):
    if re.search(r'(?:create_pull_request|pull_request_create)$', event.get('tool_name', '')):
        return True
    if event.get('tool_name') not in ('Bash', 'exec_command'):
        return False
    command = tool_command(event)
    # A heredoc is opaque content. Inspect its command line, not source/examples written to disk.
    first = command.split('\n', 1)[0] if '<<' in command else command
    try:
        tokens = shell_tokens(first)
    except ValueError:
        return bool(re.match(r'\s*gh\s+pr\s+create\b', first))
    for i in range(len(tokens) - 2):
        if Path(tokens[i]).name != 'gh' or tokens[i+1:i+3] != ['pr', 'create']:
            continue
        if i == 0 or tokens[i-1] in ('&&', '||', ';', '|', '&', '(') or tokens[0] in ('env', 'command', 'exec'):
            return True
    return False


def pending_target(event):
    name = event.get('tool_name', '')
    args = tool_arguments(event)
    if re.search(r'(?:create_pull_request|pull_request_create)$', name):
        owner, repo = args.get('owner'), args.get('repo')
        full_name = args.get('repository_full_name')
        if isinstance(full_name, str) and full_name.count('/') == 1:
            owner, repo = full_name.split('/')
        if args.get('head_repo'):
            raise Unchecked('Cross-repository MCP heads need a separate explicitly targeted check; no target was approved.')
        if not isinstance(owner, str) or not isinstance(repo, str):
            raise Unchecked('This MCP input schema is not supported; use an explicit gh pr create call.')
        host = args.get('hostname', 'github.com')
        if not isinstance(host, str):
            raise Unchecked('The MCP repository host is invalid.')
        return target('/'.join((host, owner, repo)), args.get('base') or args.get('base_branch'),
                      args.get('head') or args.get('head_branch'))
    command = tool_command(event)
    # Only a single literal invocation. Do not emulate shell expansion, wrappers, cwd changes or aliases.
    if any(c in command for c in ('$','`','\n','\r')):
        raise Unchecked('Use a separate literal gh pr create command with --repo, --base and --head.')
    try:
        tokens = shell_tokens(command)
    except ValueError:
        raise Unchecked('The PR creation command could not be read.') from None
    if len(tokens) < 3 or Path(tokens[0]).name != 'gh' or tokens[1:3] != ['pr', 'create']:
        raise Unchecked('Use a separate gh pr create invocation, without wrappers or chained commands.')
    values = {}
    value_flags = {'--repo': 'repository', '-R': 'repository', '--base': 'base', '-B': 'base',
                   '--head': 'head', '-H': 'head', '--title': None, '-t': None, '--body': None, '-b': None,
                   '--body-file': None, '-F': None, '--assignee': None, '-a': None, '--label': None,
                   '-l': None, '--milestone': None, '-m': None, '--project': None, '-p': None,
                   '--reviewer': None, '-r': None, '--template': None, '-T': None}
    switches = {'--draft', '-d', '--fill', '-f', '--fill-first', '--fill-verbose', '--no-maintainer-edit'}
    i = 3
    while i < len(tokens):
        flag, equals, value = tokens[i].partition('=')
        if flag in switches and not equals:
            i += 1
            continue
        if flag not in value_flags:
            raise Unchecked('Unsupported PR command form; use separate literal flags and no shell operators.')
        if not equals:
            i += 1
            if i >= len(tokens):
                raise Unchecked('A PR command flag has no value.')
            value = tokens[i]
        key = value_flags[flag]
        if key:
            if key in values:
                raise Unchecked('Repeated repository, base or head flag is ambiguous.')
            values[key] = value
        i += 1
    return target(values.get('repository'), values.get('base'), values.get('head'))


def remote_commit(root, selected, branch):
    endpoint = f"repos/{selected['repository']}/git/ref/heads/{quote(branch, safe='')}"
    try:
        result = subprocess.run(['gh', 'api', '--hostname', selected['host'], endpoint], cwd=root,
                                capture_output=True, text=True, timeout=8)
        data = json.loads(result.stdout) if result.returncode == 0 else {}
        oid = data.get('object', {}).get('sha')
    except (OSError, ValueError, AttributeError, subprocess.TimeoutExpired):
        oid = None
    if not isinstance(oid, str) or not OID.fullmatch(oid):
        raise Unchecked('The remote base/head commit could not be retrieved with gh; check authentication and branches.')
    if wip.git(root, 'cat-file', '-e', f'{oid}^{{commit}}').returncode:
        raise Unchecked('The remote commit is not in this repository; fetch the target before retrying.')
    return oid


def inspect(root, selected):
    if (selected['host'], selected['repository']) not in remote_repositories(root):
        raise Unchecked('The pending repository does not match any local remote, including its host.')
    base = remote_commit(root, selected, selected['base'])
    head = remote_commit(root, selected, selected['head'])
    directory = wip.wip_path(root, head)
    diff = wip.git(root, 'diff', '--name-only', '--no-renames', '-z', f'{base}...{head}')
    if diff.returncode:
        raise Unchecked('The merge base or changed paths could not be read.')
    names = sorted({PurePosixPath(p).relative_to(directory).parts[0] for p in diff.stdout.split('\0')
                    if p and wip.under(p, directory) and len(PurePosixPath(p).relative_to(directory).parts) > 1})
    rows = []
    for name in names:
        path = f'{directory}/{name}'
        kind = wip.git(root, 'cat-file', '-t', f'{head}:{path}')
        if name.startswith('.') or kind.stdout.strip() != 'tree':
            continue  # Removed records are handled by sweep, not completion review.
        shown = wip.git(root, 'show', f'{head}:{path}/status.json')
        state, problem = (None, 'status.json is missing') if shown.returncode else wip.parse_status(shown.stdout)
        rows.append({'path': path, 'status': state, 'problem': problem})
    return {**selected, 'baseCommit': base, 'headCommit': head, 'records': rows}


def receipt_path(root, result):
    # Per-worktree Git storage; a decision never leaks to another checkout or target.
    location = wip.git(root, 'rev-parse', '--git-path', 'hq/pr-preflight').stdout.strip()
    if not location:
        raise Unchecked('The local review storage could not be located.')
    key = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return root / location / (key + '.json')


def reviewed(root, result):
    path = receipt_path(root, result)
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        return data.get('target') == result and isinstance(data.get('reason'), str) and bool(data['reason'].strip())
    except (ValueError, AttributeError):
        raise Unchecked('The saved review is invalid; review this target again.') from None


def deny(message):
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'deny',
                                  'permissionDecisionReason': 'HQ PR preflight: ' + message}}


def handle(event):
    if event.get('hook_event_name') != 'PreToolUse' or not creation_candidate(event):
        return None
    try:
        selected = pending_target(event)
        cwd = tool_arguments(event).get('workdir') or event.get('cwd')
        if not isinstance(cwd, str) or not Path(cwd).is_dir():
            raise Unchecked('The tool working directory could not be determined.')
        root = wip.repository_root(cwd)
        result = inspect(root, selected)
        errors = [f"{r['path']}: {r['problem']}" for r in result['records'] if r['problem']]
        if errors:
            return deny('Record state is unchecked: ' + '; '.join(errors) + '. Fix, commit and push before retrying.')
        pending = [r for r in result['records'] if r['status']['status'] != 'done']
        if not pending or reviewed(root, result):
            return None
        rows = ', '.join(f"{r['path']} ({r['status']['status']})" for r in pending)
        command = shlex.join([sys.executable, str(Path(__file__).resolve()), '--repo', str(root),
                              '--repository', selected['host'] + '/' + selected['repository'],
                              '--base', selected['base'], '--head', selected['head'], '--reviewed',
                              '--reason', '<explain why this is an intermediate PR>'])
        return deny(f"Review before creating this PR (base {result['baseCommit'][:12]}, head {result['headCommit'][:12]}): "
                    f'{rows}. Read the records and decide whether this is the final PR. If final, verify Done When, '
                    'set done, commit and push, then retry. If intermediate, leave the state and save your reason with: '
                    + command + '. Then retry the original PR creation. Do not mark done just to pass this check.')
    except (Unchecked, wip.WipError) as error:
        return deny(f'Unchecked: {error}')
    except Exception:
        return deny('Unchecked: preflight failed. Inspect the target and fix the check before retrying; no state was approved.')


def main():
    if len(sys.argv) == 1:
        try:
            output = handle(json.load(sys.stdin))
        except Exception:
            output = deny('Unchecked: hook input could not be read.')
        if output:
            print(json.dumps(output, ensure_ascii=False))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.')
    parser.add_argument('--repository', required=True, help='[host/]owner/repo')
    parser.add_argument('--base', required=True)
    parser.add_argument('--head', required=True)
    parser.add_argument('--reviewed', action='store_true', help='record the agent decision for an intermediate PR')
    parser.add_argument('--reason')
    args = parser.parse_args()
    try:
        root = wip.repository_root(args.repo)
        result = inspect(root, target(args.repository, args.base, args.head))
        if any(r['problem'] for r in result['records']):
            raise Unchecked('Record state is invalid or missing; fix, commit and push it first.')
        if args.reviewed:
            if not args.reason or not args.reason.strip():
                raise Unchecked('A reason for keeping this PR intermediate is required.')
            path = receipt_path(root, result)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Atomic replacement avoids partial reviews on interruption or concurrent writes.
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False, encoding='utf-8') as out:
                    temporary = Path(out.name)
                    json.dump({'target': result, 'reason': args.reason.strip()}, out, ensure_ascii=False)
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (Unchecked, wip.WipError, OSError, UnicodeError) as error:
        print(f'HQ PR preflight unchecked: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
