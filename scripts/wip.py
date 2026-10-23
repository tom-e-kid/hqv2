#!/usr/bin/env python3
"""List work records, find finished ones safe to delete, and check a change against the SOT."""

import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

STATUSES = ("active", "paused", "done")
DEFAULTS = {"wip": "wip", "sdd": "docs"}


class WipError(Exception):
    pass


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def repository_root(cwd):
    result = git(cwd, "rev-parse", "--show-toplevel")
    if result.returncode:
        raise WipError("Not a Git working tree")
    return Path(result.stdout.strip())


def setting_path(root, key):
    """Return <key>.path from the shared settings, relative to the repository root."""
    value = DEFAULTS[key]
    settings = root / ".hq/v2/settings.json"
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except ValueError:
            raise WipError(".hq/v2/settings.json is not valid JSON") from None
        if not isinstance(data, dict):
            raise WipError(".hq/v2/settings.json must be an object")
        if key in data:
            section = data[key]
            value = section.get("path") if isinstance(section, dict) else None
            if not isinstance(value, str) or not value or value.strip() != value:
                raise WipError(f"{key}.path must be a non-empty string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise WipError(f"{key}.path must stay inside the repository")
    return path


def wip_path(root):
    return setting_path(root, "wip")


def sdd_path(root):
    return setting_path(root, "sdd")


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
    if not isinstance(data.get("sotImpact"), bool):
        return None, "sotImpact must be true or false"
    prs = data.get("prs", [])
    if not isinstance(prs, list) or not all(is_number(n) and n > 0 for n in prs):
        return None, "prs must be a list of PR numbers"
    return {"status": data["status"], "sotImpact": data["sotImpact"], "prs": prs}, None


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


def verify_base(root, base):
    if git(root, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").returncode:
        raise WipError("Base revision not found; fetch it or pass an existing revision")


def sweepable(root, base):
    verify_base(root, base)
    result = []
    for record in records(root):
        state, detail = classify(root, base, record)
        result.append({**record, "result": state, "detail": detail})
    return result


def under(path, directory):
    prefix = directory.as_posix()
    return path == prefix or path.startswith(prefix + "/")


FINDINGS = {
    "sot-not-updated": "The record expects an SOT change, but this change updates only the implementation. "
                       "Check the implementation against the SOT; update the SOT with agreement, align the "
                       "implementation, or confirm that an earlier change of this work already updated it.",
    "impact-mismatch": "This change updates the SOT, but the record says sotImpact is false. Review the judgment.",
    "sot-without-record": "This change updates the SOT without a work record in the change. "
                          "Work that changes the SOT needs a record.",
}


def check_pr(root, base):
    """Compare the SOT impact recorded in this change with what the change does to the SOT."""
    verify_base(root, base)
    records_dir, sot_dir = wip_path(root), sdd_path(root)
    # Only committed changes form the PR; the merge base keeps unrelated base updates out.
    diff = git(root, "diff", "--name-only", "-z", f"{base}...HEAD")
    if diff.returncode:
        raise WipError("Changed files could not be listed")
    paths = [path for path in diff.stdout.split("\0") if path]
    sot_changed = any(under(path, sot_dir) for path in paths)
    implementation = any(not under(path, records_dir) and not under(path, sot_dir) for path in paths)
    names = sorted({PurePosixPath(path).relative_to(records_dir).parts[0] for path in paths
                    if under(path, records_dir) and len(PurePosixPath(path).relative_to(records_dir).parts) > 1})
    records, findings = [], []
    for name in names:
        path = f"{records_dir.as_posix()}/{name}"
        shown = git(root, "show", f"HEAD:{path}/status.json")
        if shown.returncode:
            continue  # Removed by this change, for example when sweeping finished records.
        status, problem = parse_status(shown.stdout)
        records.append({"name": name, "path": path, "status": status, "problem": problem})
        # The SOT may lead the implementation; only an implementation that moves alone is a divergence risk.
        if problem:
            findings.append({"code": "invalid-status", "record": name, "detail": problem})
        elif status["sotImpact"] and implementation and not sot_changed:
            findings.append({"code": "sot-not-updated", "record": name, "detail": FINDINGS["sot-not-updated"]})
        elif not status["sotImpact"] and sot_changed:
            findings.append({"code": "impact-mismatch", "record": name, "detail": FINDINGS["impact-mismatch"]})
    if sot_changed and not records:
        findings.append({"code": "sot-without-record", "record": None, "detail": FINDINGS["sot-without-record"]})
    return {"base": base, "sotPath": sot_dir.as_posix(), "sotChanged": sot_changed,
            "implementationChanged": implementation, "records": records, "findings": findings}


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
            rows = check_pr(root, args.base)
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
        print(f"SOT ({rows['sotPath']}) changed: {'yes' if rows['sotChanged'] else 'no'}; "
              f"work records in the change: {len(rows['records'])}")
        for finding in rows["findings"]:
            print(f"{finding['code']}: {finding['record'] or '-'}: {finding['detail']}")
        if not rows["findings"]:
            print("no findings")
        return 0
    if not rows:
        print("no work records")
        return 0
    table = []
    for row in rows:
        status = row["status"] or {}
        table.append({"name": row["name"], "status": status.get("status", "-"), "sot": {True: "yes", False: "no"}.get(status.get("sotImpact"), "-"),
                      "prs": ",".join(f"#{n}" for n in status.get("prs", [])) or "-",
                      "note": row.get("detail") if args.action == "sweepable" else (row["problem"] or ""),
                      "result": row.get("result", "")})
    columns = [("NAME", "name"), ("STATUS", "status"), ("SOT", "sot"), ("PRS", "prs")]
    columns += [("RESULT", "result"), ("DETAIL", "note")] if args.action == "sweepable" else [("PROBLEM", "note")]
    show(table, columns)
    return 0


if __name__ == "__main__":
    sys.exit(main())
