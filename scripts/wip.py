#!/usr/bin/env python3
"""List work records, find finished ones safe to delete, and remind to review the SSOT for a change."""

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

STATUSES = ("active", "paused", "done")
DEFAULTS = {"wip": "wip"}


class WipError(Exception):
    pass


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def repository_root(cwd):
    result = git(cwd, "rev-parse", "--show-toplevel")
    if result.returncode:
        raise WipError("Not a Git working tree")
    return Path(result.stdout.strip())


def settings(root, revision=None):
    """Return the shared settings from the working tree, or from a commit when a revision is given."""
    if revision is not None:
        shown = git(root, "show", f"{revision}:.hq/v2/settings.json")
        text = None if shown.returncode else shown.stdout
    else:
        path = root / ".hq/v2/settings.json"
        text = path.read_text(encoding="utf-8") if path.is_file() else None
    if text is None:
        return {}
    try:
        data = json.loads(text)
    except ValueError:
        raise WipError(".hq/v2/settings.json is not valid JSON") from None
    if not isinstance(data, dict):
        raise WipError(".hq/v2/settings.json must be an object")
    return data


def repository_path(value, name):
    """Return a path relative to the repository root."""
    if not isinstance(value, str) or not value or value.strip() != value:
        raise WipError(f"{name} must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise WipError(f"{name} must stay inside the repository")
    return path


def wip_path(root, revision=None):
    data = settings(root, revision)
    if "wip" not in data:
        return PurePosixPath(DEFAULTS["wip"])
    section = data["wip"]
    return repository_path(section.get("path") if isinstance(section, dict) else None, "wip.path")


def ssot_paths(root, revision=None):
    """Return the registered SSOT paths, or None when the project defines no SSOT.

    The SSOT is never inferred from locations or file names, so there is no default."""
    data = settings(root, revision)
    if "ssot" not in data:
        return None
    section = data["ssot"]
    values = section.get("paths") if isinstance(section, dict) else None
    if not isinstance(values, list) or not values:
        raise WipError("ssot.paths must be a non-empty list of paths")
    paths = [repository_path(value, "each ssot.paths entry") for value in values]
    # The root would make every implementation change an SSOT change.
    if PurePosixPath(".") in paths:
        raise WipError("ssot.paths must not include the repository root")
    return paths


def is_number(value):
    return isinstance(value, int) and not isinstance(value, bool)


def parse_status(text):
    """Return (status, problem); problem is None only for a valid status.json."""
    try:
        data = json.loads(text)
    except ValueError:
        return None, "status.json is not valid JSON"
    if not isinstance(data, dict):
        return None, "status.json must be an object"
    if data.get("status") not in STATUSES:
        return None, "status must be active, paused or done"
    if not isinstance(data.get("ssotImpact"), bool):
        return None, "ssotImpact must be true or false"
    prs = data.get("prs", [])
    if not isinstance(prs, list) or not all(is_number(n) and n > 0 for n in prs):
        return None, "prs must be a list of PR numbers"
    return {"status": data["status"], "ssotImpact": data["ssotImpact"], "prs": prs}, None


def records(root):
    base = root / wip_path(root)
    if not base.is_dir():
        return []
    found = []
    # Links are not followed so a record cannot point outside the repository.
    for directory in sorted(base.iterdir()):
        if directory.is_symlink() or not directory.is_dir() or directory.name.startswith("."):
            continue
        status_file = directory / "status.json"
        if status_file.is_file() and not status_file.is_symlink():
            status, problem = parse_status(status_file.read_text(encoding="utf-8"))
        else:
            status, problem = None, "status.json is missing"
        found.append({"name": directory.name, "path": directory.relative_to(root).as_posix(),
                      "status": status, "problem": problem})
    return found


def classify(root, base, record):
    """Return (result, detail) for deletion; only "deletable" permits removing the record."""
    if record["problem"]:
        return "invalid", record["problem"]
    if record["status"]["status"] != "done":
        return "not-done", record["status"]["status"]
    on_base = git(root, "show", f"{base}:{record['path']}/status.json")
    if on_base.returncode:
        return "waiting", "the record is not on the base revision yet"
    status, problem = parse_status(on_base.stdout)
    if problem or status["status"] != "done":
        return "waiting", "the base revision does not have the done state yet"
    # Compare both the working tree and the index: a staged edit can hide behind a reverted file.
    for scope in ((), ("--cached",)):
        if git(root, "diff", "--quiet", *scope, base, "--", record["path"]).returncode:
            return "changed", "the record differs from the base revision"
    # Compare the disk with tracked files: Git status hides ignored files such as local evidence.
    tracked = git(root, "ls-files", "-z", "--", record["path"])
    if tracked.returncode:
        return "changed", "tracked files could not be listed"
    known = set(filter(None, tracked.stdout.split("\0")))
    for item in sorted((root / record["path"]).rglob("*")):
        if (item.is_file() or item.is_symlink()) and item.relative_to(root).as_posix() not in known:
            return "changed", "the record has files that are not in Git"
    return "deletable", "the done record is on the base revision"


def commit(root, revision, label="Base"):
    """Return the commit ID so later steps keep the same target even if the checkout moves."""
    result = git(root, "rev-parse", "--verify", "--quiet", f"{revision}^{{commit}}")
    if result.returncode:
        raise WipError(f"{label} revision not found; fetch it or pass an existing revision")
    return result.stdout.strip()


def sweepable(root, base):
    commit(root, base)
    result = []
    for record in records(root):
        state, detail = classify(root, base, record)
        result.append({**record, "result": state, "detail": detail})
    return result


def under(path, directory):
    prefix = directory.as_posix()
    return path == prefix or path.startswith(prefix + "/")


REVIEW_SSOT = ("This change updates the implementation but not the SSOT, and its work records say the work may "
               "affect what the SSOT covers. Check whether the SSOT needs a review or an update, and tell the user "
               "the conclusion. The SSOT already covering it, an earlier PR having updated it, or not changing the "
               "decision yet are valid conclusions. This is a reminder, not a consistency check.")


def check_pr(root, base, head="HEAD"):
    """Remind to review the SSOT when a change with SSOT impact updates the implementation but not the SSOT.

    No reminder does not mean the SSOT and the implementation agree; it only means the condition is not met."""
    base, head = commit(root, base), commit(root, head, "Head")
    # Settings and records come from the head commit, so uncommitted edits never mix in.
    records_dir, ssot = wip_path(root, head), ssot_paths(root, head)
    result = {"base": base, "head": head, "ssotPaths": None, "ssotChanged": False, "implementationChanged": False,
              "records": [], "notices": [], "problems": []}
    if ssot is None:
        return result  # No SSOT is defined, so the check does not apply.
    result["ssotPaths"] = [path.as_posix() for path in ssot]
    missing = [path.as_posix() for path in ssot if git(root, "cat-file", "-e", f"{head}:{path.as_posix()}").returncode]
    if missing:
        result["problems"].append({"code": "ssot-missing", "record": None,
                                   "detail": "Registered SSOT paths are not in the head commit: " + ", ".join(missing)})
        if len(missing) == len(ssot):
            return result
    # The merge base keeps unrelated base updates out, as in the pull request.
    diff = git(root, "diff", "--name-only", "-z", f"{base}...{head}")
    if diff.returncode:
        raise WipError("Changed files could not be listed")
    paths = [path for path in diff.stdout.split("\0") if path and not under(path, records_dir)]
    result["ssotChanged"] = any(under(path, item) for path in paths for item in ssot)
    result["implementationChanged"] = any(not any(under(path, item) for item in ssot) for path in paths)
    changed = [path for path in diff.stdout.split("\0") if path and under(path, records_dir)]
    names = sorted({PurePosixPath(path).relative_to(records_dir).parts[0] for path in changed
                    if len(PurePosixPath(path).relative_to(records_dir).parts) > 1})
    for name in names:
        path = f"{records_dir.as_posix()}/{name}"
        # Like records(), hidden entries and anything but a directory are not records.
        if name.startswith(".") or git(root, "cat-file", "-t", f"{head}:{path}").stdout.strip() != "tree":
            continue  # Includes a record removed by this change, for example when sweeping finished records.
        shown = git(root, "show", f"{head}:{path}/status.json")
        status, problem = (None, "status.json is missing") if shown.returncode else parse_status(shown.stdout)
        result["records"].append({"name": name, "path": path, "status": status, "problem": problem})
        if problem:
            result["problems"].append({"code": "invalid-status", "record": name, "detail": problem})
    impacting = [record["name"] for record in result["records"] if record["status"] and record["status"]["ssotImpact"]]
    # Touching a record does not show that its work changed anything here, so the reminder never blames a record.
    if impacting and result["implementationChanged"] and not result["ssotChanged"]:
        result["notices"].append({"code": "ssot-review", "records": impacting, "detail": REVIEW_SSOT})
    return result


def show(rows, columns):
    widths = [max(len(name), *(len(str(row[key])) for row in rows)) for name, key in columns]
    print("  ".join(name.ljust(width) for (name, _), width in zip(columns, widths)).rstrip())
    for row in rows:
        print("  ".join(str(row[key]).ljust(width) for (_, key), width in zip(columns, widths)).rstrip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "sweepable", "check-pr"))
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", help="base revision for sweepable and check-pr, for example origin/develop")
    parser.add_argument("--head", default="HEAD", help="head revision for check-pr (default: HEAD)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        root = repository_root(args.repo)
        if args.action == "list":
            rows = records(root)
        elif not args.base:
            raise WipError(f"{args.action} needs --base")
        elif args.action == "sweepable":
            rows = sweepable(root, args.base)
        else:
            rows = check_pr(root, args.base, args.head)
    except WipError as error:
        # Messages are static; raw Git output may contain local paths.
        print(f"wip: {error}", file=sys.stderr)
        return 2
    except (OSError, UnicodeDecodeError):
        print("wip: reading the work records failed", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if args.action == "check-pr":
        if rows["ssotPaths"] is None:
            print("SSOT: not defined (ssot.paths); the check does not apply")
            return 0
        answer = {True: "yes", False: "no"}
        print(f"SSOT ({', '.join(rows['ssotPaths'])}) changed: {answer[rows['ssotChanged']]}; "
              f"implementation changed: {answer[rows['implementationChanged']]}; "
              f"work records in the change: {len(rows['records'])}")
        for notice in rows["notices"]:
            print(f"{notice['code']}: {', '.join(notice['records'])}: {notice['detail']}")
        for problem in rows["problems"]:
            print(f"cannot judge: {problem['code']}: {problem['record'] or '-'}: {problem['detail']}")
        if not rows["notices"] and not rows["problems"]:
            print("no reminder (this does not confirm that the SSOT and the implementation agree)")
        return 0
    if not rows:
        print("no work records")
        return 0
    table = []
    for row in rows:
        status = row["status"] or {}
        table.append({"name": row["name"], "status": status.get("status", "-"), "ssot": {True: "yes", False: "no"}.get(status.get("ssotImpact"), "-"),
                      "prs": ",".join(f"#{n}" for n in status.get("prs", [])) or "-",
                      "note": row.get("detail") if args.action == "sweepable" else (row["problem"] or ""),
                      "result": row.get("result", "")})
    columns = [("NAME", "name"), ("STATUS", "status"), ("SSOT", "ssot"), ("PRS", "prs")]
    columns += [("RESULT", "result"), ("DETAIL", "note")] if args.action == "sweepable" else [("PROBLEM", "note")]
    show(table, columns)
    return 0


if __name__ == "__main__":
    sys.exit(main())
