#!/usr/bin/env python3
"""After an agent creates a pull request, advise when it may let the implementation diverge from the SOT."""

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
REMOTE_URL = re.compile(r"^(?:[a-z][a-z0-9+.-]*://)?(?:[^@/\s]+@)?[^/:\s]+(?::\d+)?[:/](.+?)(?:\.git)?/*$", re.I)
OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")


class Unchecked(Exception):
    """The created pull request could not be tied to commits in this repository."""


def created_pull_request(event):
    """Return (owner/repo, URL) of the single pull request named in the tool result."""
    output = json.dumps(event.get("tool_response", ""), ensure_ascii=False)
    found = {(f"{match[2]}/{match[3]}".lower(), f"https://{match[1].lower()}/{match[2]}/{match[3]}/pull/{match[4]}".lower())
             for match in PR_URL.finditer(output)}
    if len(found) != 1:
        raise Unchecked("the tool result does not name exactly one pull request")
    return found.pop()


def remote_repositories(root):
    """Return owner/repo of every remote; the same commits may exist in another repository."""
    found = set()
    for line in wip.git(root, "remote", "-v").stdout.splitlines():
        parts = line.split()
        match = REMOTE_URL.match(parts[1]) if len(parts) > 1 else None
        if match:
            found.add(match[1].lower())
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


def uses_records(root, *revisions):
    """Whether any of the commits keeps work records; an invalid wip.path counts so it is not hidden."""
    for revision in revisions:
        try:
            path = wip.wip_path(root, revision).as_posix()
        except wip.WipError:
            return True
        if wip.git(root, "cat-file", "-t", f"{revision}:{path}").stdout.strip() == "tree":
            return True
    return False


def check(root, event):
    """Return (URL, result) for the created pull request, None when it keeps no records, or raise Unchecked."""
    repository, url = created_pull_request(event)
    if repository not in remote_repositories(root):
        raise Unchecked("this repository has no remote for the pull request's repository")
    head, base = pull_request_commits(root, url)
    for revision in (head, base):
        if wip.git(root, "cat-file", "-e", f"{revision}^{{commit}}").returncode:
            raise Unchecked("the pull request's head or base commit is not in this repository; fetch it")
    # Stay quiet in repositories that do not keep work records.
    if not uses_records(root, base, head):
        return None
    return url, wip.check_pr(root, base, head)


def context(message):
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message}}


def handle(event):
    if event.get("hook_event_name") != "PostToolUse" or not creation_candidate(event):
        return None
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not cwd or not Path(cwd).is_dir():
        return None
    try:
        root = wip.repository_root(cwd)
    except wip.WipError:
        return None  # Without a repository there are no commits to check.
    try:
        checked = check(root, event)
    except Unchecked as error:
        if not uses_records(root, "HEAD"):
            return None
        return context(f"HQ SOT check not run: {error}. Run scripts/wip.py check-pr with --base and --head "
                       "set to the pull request's commits to check SOT alignment.")
    except wip.WipError as error:
        return context(f"HQ SOT check could not run: {error}.")
    if checked is None or not checked[1]["findings"]:
        return None
    url, result = checked
    lines = [f"- {item['code']} ({item['record'] or 'no record'}): {item['detail']}" for item in result["findings"]]
    return context(f"HQ SOT check of {url} (base {result['base'][:12]}, head {result['head'][:12]}): the SOT "
                   f"({result['sotPath']}) and the implementation may diverge. Tell the user, and resolve it "
                   "in this PR or by agreement.\n" + "\n".join(lines))


def main():
    try:
        result = handle(json.load(sys.stdin))
        if result:
            print(json.dumps(result, ensure_ascii=False))
    except Exception:
        # Advisory only: never fail the tool call or print raw hook input.
        print("HQ SOT check: hook failed; SOT alignment was not checked", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
