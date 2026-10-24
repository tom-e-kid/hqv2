#!/usr/bin/env python3
"""After an agent creates a pull request, remind it to review the SSOT when the PR may have skipped that."""

import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import wip

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pr_event import creation_candidate

GH_TIMEOUT = 20
PR_URL = re.compile(r"https://([\w.-]+)/([\w.-]+)/([\w.-]+)/pull/(\d+)(?!\d)")
REMOTE_URL = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/\s]+@)?([^/:\s]+)(?::\d+)?[:/](.+?)(?:\.git)?/*$", re.I)
OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


class Unchecked(Exception):
    """The created pull request could not be tied to commits in this repository."""


def created_pull_request(event):
    """Return ((host, owner/repo), URL) of the single pull request named in the tool result."""
    output = json.dumps(event.get("tool_response", ""), ensure_ascii=False)
    found = {((match[1].lower(), f"{match[2]}/{match[3]}".lower()),
              f"https://{match[1].lower()}/{match[2]}/{match[3]}/pull/{match[4]}".lower())
             for match in PR_URL.finditer(output)}
    if len(found) != 1:
        raise Unchecked("the tool result does not name exactly one pull request")
    return found.pop()


def remote_repositories(root):
    """Return (host, owner/repo) of every remote; the same commits may exist in another repository.

    Hosts are compared as written, so an SSH host alias does not match and the PR stays unchecked."""
    found = set()
    for line in wip.git(root, "remote", "-v").stdout.splitlines():
        parts = line.split()
        match = REMOTE_URL.match(parts[1]) if len(parts) > 1 else None
        if match:
            found.add((match[1].lower(), match[2].lower()))
    return found


def pull_request_commits(root, url):
    """Return the (head, base) commit IDs that GitHub reports for the pull request."""
    try:
        result = subprocess.run(["gh", "pr", "view", url, "--json", "headRefOid,baseRefOid"], cwd=root,
                                capture_output=True, text=True, timeout=GH_TIMEOUT)
        data = json.loads(result.stdout) if not result.returncode else {}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        data = {}
    commits = (data.get("headRefOid"), data.get("baseRefOid")) if isinstance(data, dict) else (None, None)
    if not all(isinstance(value, str) and OBJECT_ID.fullmatch(value) for value in commits):
        raise Unchecked("the pull request's head and base commits could not be retrieved with gh")
    return commits


def check(event):
    """Return (URL, check result) for the created pull request, or raise Unchecked."""
    repository, url = created_pull_request(event)
    cwd = event.get("cwd")
    try:
        root = wip.repository_root(cwd) if isinstance(cwd, str) and cwd and Path(cwd).is_dir() else None
    except wip.WipError:
        root = None
    if root is None:
        raise Unchecked("the working directory is not in a Git repository")
    if repository not in remote_repositories(root):
        raise Unchecked("this repository has no remote for the pull request's repository")
    head, base = pull_request_commits(root, url)
    for revision in (head, base):
        if wip.git(root, "cat-file", "-e", f"{revision}^{{commit}}").returncode:
            raise Unchecked("the pull request's head or base commit is not in this repository; fetch it")
    return url, wip.check_pr(root, base, head)


def context(message):
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message}}


def handle(event):
    if event.get("hook_event_name") != "PostToolUse" or not creation_candidate(event):
        return None
    try:
        checked = check(event)
    except Unchecked as error:
        # Without the PR's commits nothing shows whether an SSOT is defined, so report instead of staying quiet.
        return context(f"HQ SSOT check not run: {error}. Run scripts/wip.py check-pr with --base and --head "
                       "set to the pull request's commits to check whether the SSOT needs a review.")
    except wip.WipError as error:
        return context(f"HQ SSOT check could not run: {error}.")
    url, result = checked
    # Quiet also when no SSOT is defined: the check does not apply there.
    if not result["notices"] and not result["problems"]:
        return None
    lines = [f"HQ SSOT check of {url} (base {result['base'][:12]}, head {result['head'][:12]}, "
             f"SSOT: {', '.join(result['ssotPaths'])}):"]
    lines += [f"- {item['code']} (records: {', '.join(item['records'])}): {item['detail']}" for item in result["notices"]]
    lines += [f"- could not judge, {item['code']} ({item['record'] or 'no record'}): {item['detail']}"
              for item in result["problems"]]
    return context("\n".join(lines))


def main():
    try:
        result = handle(json.load(sys.stdin))
        if result:
            print(json.dumps(result, ensure_ascii=False))
    except Exception:
        # Advisory only: never fail the tool call or print raw hook input.
        print("HQ SSOT check: hook failed; the PR was not checked", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
