#!/usr/bin/env python3
"""Advise at pull request creation when a change may let the implementation diverge from the SOT."""

import json
import os
from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import wip

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pr_event import creation_candidate, tool_arguments, tool_command

OPERATORS = set("();<>|&")


class Unresolved(Exception):
    """The checkout, branch or base that the PR is created from could not be determined."""


def shell_words(command):
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    return list(lexer)


def option(arguments, long, short):
    """Return the value of an option such as --base/-B, or None when it is absent."""
    for index, word in enumerate(arguments):
        if word in (long, short):
            return arguments[index + 1] if index + 1 < len(arguments) else ""
        if word.startswith(long + "="):
            return word.split("=", 1)[1]
    return None


def change_directory(directory, arguments):
    """Follow a literal `cd <dir>`; anything the shell must evaluate is not resolved."""
    target = arguments[0] if arguments else "~"
    if len(arguments) > 1 or target == "-" or "$" in target or "`" in target:
        raise Unresolved("the directory the command runs in could not be determined")
    return directory / os.path.expanduser(target)


def shell_call(command, directory):
    """Return (directory, head, base) of the first `gh pr create`, or None when the command does not run it."""
    try:
        words = shell_words(command)
    except ValueError:
        raise Unresolved("the command could not be parsed") from None
    starts = [index for index in range(len(words) - 2)
              if os.path.basename(words[index]) == "gh" and words[index + 1:index + 3] == ["pr", "create"]]
    if not starts:
        return None
    # Commands before the PR creation may move to another checkout, such as a work tree.
    segments, current, separators = [], [], set()
    for word in words[:starts[0]]:
        if set(word) <= OPERATORS:
            separators.add(word)
            segments.append(current)
            current = []
        else:
            current.append(word)
    moves = [segment for segment in segments if segment and segment[0] in ("cd", "pushd", "popd")]
    if moves and not separators <= {"&&", ";"}:
        raise Unresolved("the directory the command runs in could not be determined")
    for segment in moves:
        if segment[0] == "popd":
            raise Unresolved("the directory the command runs in could not be determined")
        directory = change_directory(directory, segment[1:])
    arguments = []
    for word in words[starts[0] + 3:]:
        if set(word) <= OPERATORS:
            break
        arguments.append(word)
    if "GH_REPO" in command or option(arguments, "--repo", "-R") is not None:
        raise Unresolved("the PR targets a repository named by --repo or GH_REPO")
    return directory, option(arguments, "--head", "-H"), option(arguments, "--base", "-B")


def creation_call(event, directory):
    """Return (directory, head, base) that the PR is created from, or None when no PR is created."""
    if tool_command(event):
        return shell_call(tool_command(event), directory)
    # MCP tools run outside the shell; their arguments name the branches.
    arguments = tool_arguments(event)

    def pick(*keys):
        return next((arguments[key] for key in keys if isinstance(arguments.get(key), str) and arguments[key]), None)
    return directory, pick("head", "head_branch", "headBranch"), pick("base", "base_branch", "baseBranch")


def git_settings(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except (OSError, ValueError):
        return {}
    section = data.get("git") if isinstance(data, dict) else None
    return section if isinstance(section, dict) else {}


def configured_target(root, branch):
    """Return (remote, base) for the branch; checkout-local settings override shared ones."""
    sources = (git_settings(root / ".hq/v2/.ignore/settings.json"), git_settings(root / ".hq/v2/settings.json"))
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


def base_revision(root, branch, requested):
    remote, configured = configured_target(root, branch)
    base = requested or configured
    if not isinstance(base, str) or not base:
        return None
    candidates = [f"{remote}/{base}"] if isinstance(remote, str) and remote else []
    for candidate in candidates + [base]:
        if not wip.git(root, "rev-parse", "--verify", "--quiet", f"{candidate}^{{commit}}").returncode:
            return candidate
    return None


def context(message):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": message}}


def keeps_records(directory):
    """Whether the repository keeps work records; an invalid wip.path counts so the skip is not hidden."""
    try:
        root = wip.repository_root(directory)
    except (wip.WipError, OSError):
        return False
    try:
        return (root / wip.wip_path(root)).is_dir()
    except wip.WipError:
        return True


def check(event, cwd):
    """Return the check result, None when there is nothing to check, or raise Unresolved."""
    call = creation_call(event, Path(cwd))
    if call is None:
        return None
    directory, head, requested = call
    if not directory.is_dir():
        raise Unresolved("the directory the command runs in could not be determined")
    try:
        root = wip.repository_root(directory)
    except wip.WipError:
        return None
    branch = wip.git(root, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if head and head.split(":")[-1] != branch:
        raise Unresolved("the PR head is not the branch checked out where the command runs", root)
    base = base_revision(root, branch, requested)
    if base is None:
        raise Unresolved("the PR base branch could not be determined", root)
    # gh creates a PR only from commits ahead of the base; without any, another checkout is the source.
    if not wip.git(root, "merge-base", "--is-ancestor", "HEAD", base).returncode:
        raise Unresolved("the checked-out branch has no commits ahead of the base, so the PR is likely "
                         "created from another checkout", root)
    return base, wip.check_pr(root, base)


def handle(event):
    if event.get("hook_event_name") != "PreToolUse" or not creation_candidate(event):
        return None
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not cwd or not Path(cwd).is_dir():
        return None
    try:
        checked = check(event, cwd)
    except Unresolved as error:
        reason, *where = error.args
        # Stay quiet in repositories that do not keep work records.
        if not keeps_records(where[0] if where else cwd):
            return None
        return context(f"HQ SOT check not run: {reason}. Run scripts/wip.py check-pr with --repo and --base "
                       "in the checkout the PR is created from to check SOT alignment.")
    except wip.WipError as error:
        return context(f"HQ SOT check could not run: {error}.")
    if checked is None:
        return None
    base, result = checked
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
