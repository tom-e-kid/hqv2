#!/usr/bin/env python3
"""Advise at pull request creation when a change may let the implementation diverge from the SOT."""

import json
from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import wip

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pr_event import creation_candidate, tool_arguments, tool_command


def requested_base(event):
    """Return the base branch named in the PR creation call, if any."""
    arguments = tool_arguments(event)
    for key in ("base", "base_branch", "baseBranch"):
        if isinstance(arguments.get(key), str) and arguments[key]:
            return arguments[key]
    try:
        words = shlex.split(tool_command(event))
    except ValueError:
        return None
    for index, word in enumerate(words):
        if word in ("--base", "-B") and index + 1 < len(words):
            return words[index + 1]
        if word.startswith("--base="):
            return word.split("=", 1)[1]
    return None


def git_settings(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        return {}
    section = data.get("git") if isinstance(data, dict) else None
    return section if isinstance(section, dict) else {}


def configured_target(root):
    """Return (remote, base) for the current branch; checkout-local settings override shared ones."""
    sources = (git_settings(root / ".hq/v2/.ignore/settings.json"), git_settings(root / ".hq/v2/settings.json"))
    branch = wip.git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    for source in sources:
        branches = source.get("branches")
        target = branches.get(branch) if isinstance(branches, dict) else None
        if isinstance(target, dict):
            return target.get("remote"), target.get("baseBranch")

    def pick(key):
        for source in sources:
            if isinstance(source.get(key), str) and source[key]:
                return source[key]
        return None
    return pick("remote"), pick("baseBranch")


def base_revision(root, event):
    remote, configured = configured_target(root)
    base = requested_base(event) or configured
    if not isinstance(base, str) or not base:
        return None
    candidates = [f"{remote}/{base}"] if isinstance(remote, str) and remote else []
    for candidate in candidates + [base]:
        if not wip.git(root, "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}").returncode:
            return candidate
    return None


def context(message):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": message}}


def handle(event):
    if event.get("hook_event_name") != "PreToolUse" or not creation_candidate(event):
        return None
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    try:
        root = wip.repository_root(cwd)
    except wip.WipError:
        return None
    try:
        base = base_revision(root, event)
        if base is None:
            # Stay quiet in repositories that do not keep work records.
            if not (root / wip.wip_path(root)).is_dir():
                return None
            return context("HQ SOT check skipped: the PR base branch could not be determined. "
                           "Run scripts/wip.py check-pr with --base to check SOT alignment.")
        result = wip.check_pr(root, base)
    except wip.WipError as error:
        return context(f"HQ SOT check could not run: {error}.")
    if not result["findings"]:
        return None
    lines = [f"- {item['code']} ({item['record'] or 'no record'}): {item['detail']}" for item in result["findings"]]
    return context(f"HQ SOT check against {base}: the SOT ({result['sotPath']}) and the implementation may diverge. "
                   "This does not block the PR. Tell the user, and resolve it in this PR or by agreement.\n"
                   + "\n".join(lines))


def main():
    try:
        result = handle(json.load(sys.stdin))
        if result:
            print(json.dumps(result, ensure_ascii=False))
    except Exception:
        # Advisory only: never block PR creation or print raw hook input.
        print("HQ SOT check: hook failed; SOT alignment was not checked", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
