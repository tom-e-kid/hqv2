#!/usr/bin/env python3
"""List work records and find finished ones whose final state is already on a base revision."""

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

STATUSES = ("active", "paused", "done")
WEIGHTS = (1, 2, 3)
DEFAULT_PATH = "wip"


class WipError(Exception):
    pass


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def repository_root(cwd):
    result = git(cwd, "rev-parse", "--show-toplevel")
    if result.returncode:
        raise WipError("Not a Git working tree")
    return Path(result.stdout.strip())


def wip_path(root):
    """Return the record directory from the shared settings, relative to the repository root."""
    value = DEFAULT_PATH
    settings = root / ".hq/v2/settings.json"
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except ValueError:
            raise WipError(".hq/v2/settings.json is not valid JSON") from None
        if not isinstance(data, dict):
            raise WipError(".hq/v2/settings.json must be an object")
        if "wip" in data:
            section = data["wip"]
            value = section.get("path") if isinstance(section, dict) else None
            if not isinstance(value, str) or not value or value.strip() != value:
                raise WipError("wip.path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise WipError("wip.path must stay inside the repository")
    return path


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
    if not is_number(data.get("weight")) or data["weight"] not in WEIGHTS:
        return None, "weight must be 1, 2 or 3"
    prs = data.get("prs", [])
    if not isinstance(prs, list) or not all(is_number(n) and n > 0 for n in prs):
        return None, "prs must be a list of PR numbers"
    return {"status": data["status"], "weight": data["weight"], "prs": prs}, None


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
    # Any later edit, staged or not, means the final record is not what the base holds.
    if git(root, "diff", "--quiet", base, "--", record["path"]).returncode:
        return "changed", "the record differs from the base revision"
    untracked = git(root, "status", "--porcelain", "--untracked-files=all", "--", record["path"])
    if untracked.returncode or untracked.stdout.strip():
        return "changed", "the record has files the base revision does not have"
    return "deletable", "the done record is on the base revision"


def sweepable(root, base):
    if git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode:
        raise WipError("Base revision not found; fetch it or pass an existing revision")
    result = []
    for record in records(root):
        state, detail = classify(root, base, record)
        result.append({**record, "result": state, "detail": detail})
    return result


def show(rows, columns):
    widths = [max(len(name), *(len(str(row[key])) for row in rows)) for name, key in columns]
    print("  ".join(name.ljust(width) for (name, _), width in zip(columns, widths)).rstrip())
    for row in rows:
        print("  ".join(str(row[key]).ljust(width) for (_, key), width in zip(columns, widths)).rstrip())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "sweepable"))
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", help="base revision for sweepable, for example origin/develop")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        root = repository_root(args.repo)
        if args.action == "list":
            rows = records(root)
        else:
            if not args.base:
                raise WipError("sweepable needs --base")
            rows = sweepable(root, args.base)
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
    if not rows:
        print("no work records")
        return 0
    table = []
    for row in rows:
        status = row["status"] or {}
        table.append({"name": row["name"], "status": status.get("status", "-"), "weight": status.get("weight", "-"),
                      "prs": ",".join(f"#{n}" for n in status.get("prs", [])) or "-",
                      "note": row.get("detail") if args.action == "sweepable" else (row["problem"] or ""),
                      "result": row.get("result", "")})
    columns = [("NAME", "name"), ("STATUS", "status"), ("WEIGHT", "weight"), ("PRS", "prs")]
    columns += [("RESULT", "result"), ("DETAIL", "note")] if args.action == "sweepable" else [("PROBLEM", "note")]
    show(table, columns)
    return 0


if __name__ == "__main__":
    sys.exit(main())
