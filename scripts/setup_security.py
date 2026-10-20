#!/usr/bin/env python3
"""Install, update or inspect HQ's local, standalone Git commit guard."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parent / "commit_security.py"
HOOK = Path(__file__).resolve().parents[1] / "hooks/git/pre-commit"
OWNER = "hq-commit-security-v1"
HOOK_NAMES = ("pre-commit", "pre-merge-commit", "pre-applypatch")
# SHA-256 of earlier HQ hook templates. Only these exact copies are replaced by update or removed by uninstall.
PREVIOUS_HOOKS = {
    "8f81de0054f84bca51af29a56e2f94450a5188ac21fa860c2274ae6bff4bba90",  # v1: scan only, no <hook>.d steps
}


class SetupError(Exception):
    pass


def git(cwd, *args):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    if result.returncode:
        raise SetupError("Git operation failed; check installation status")
    return os.fsdecode(result.stdout).rstrip("\n")


def locations(cwd):
    root = Path(git(cwd, "rev-parse", "--show-toplevel"))
    common = Path(git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir"))
    return root, common / "hq-commit-security", common / "hooks/pre-commit"


def hooks_path_set(cwd):
    result = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=cwd, capture_output=True)
    if result.returncode not in {0, 1}:
        raise SetupError("Cannot read Git hook settings")
    return result.returncode == 0


def fingerprint(content):
    return hashlib.sha256(content).hexdigest()


def metadata(payload):
    if payload.is_symlink() or (payload / "manifest.json").is_symlink() or (payload / "check.py").is_symlink():
        raise SetupError("Refusing a symbolic link in the installed security payload")
    try:
        data = json.loads((payload / "manifest.json").read_text())
        if data.get("owner") != OWNER or data.get("sha256") != fingerprint((payload / "check.py").read_bytes()):
            raise ValueError
        return data
    except (OSError, ValueError, AttributeError):
        raise SetupError("Installed security payload is missing or modified; review it before setup") from None


def hook_version(candidate):
    """Return "current" or "previous" for an HQ hook copy, otherwise None."""
    if candidate.is_symlink() or not candidate.is_file():
        return None
    content = candidate.read_bytes()
    if content == HOOK.read_bytes():
        return "current"
    if fingerprint(content) in PREVIOUS_HOOKS:
        return "previous"
    return None


def status(cwd):
    _, payload, hook = locations(cwd)
    if not payload.exists() and not payload.is_symlink():
        return "not-installed"
    try:
        data = metadata(payload)
    except SetupError:
        return "damaged"
    if hooks_path_set(cwd):
        return "external-hook-unverified"
    if hook.parent.is_symlink():
        return "hook-missing-or-modified"
    outdated = False
    for name in HOOK_NAMES:
        candidate = hook.parent / name
        version = hook_version(candidate)
        if version is None or not os.access(candidate, os.X_OK):
            return "hook-missing-or-modified"
        outdated = outdated or version == "previous"
    # Steps in <hook>.d/ belong to the repository; the hook runs them but status does not vouch for them.
    if outdated or data["sha256"] != fingerprint(SOURCE.read_bytes()):
        return "update-available"
    return "ready"


def atomic_write(path, content, mode):
    if path.is_symlink():
        raise SetupError("Refusing to replace a symbolic link")
    fd, name = tempfile.mkstemp(prefix=".hq-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            os.fchmod(stream.fileno(), mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def setup(cwd, action):
    _, payload, hook = locations(cwd)
    if hook.parent.is_symlink():
        raise SetupError("Refusing a symbolic link for the Git hooks directory")
    if action == "install":
        if hooks_path_set(cwd):
            raise SetupError("Existing core.hooksPath preserved. Use prepare and integrate the check into your hook manager")
        if any((hook.parent / name).exists() or (hook.parent / name).is_symlink() for name in HOOK_NAMES):
            raise SetupError(
                "Existing Git hook preserved. Move it into <hook>.d/ to run it before the check, "
                "or use prepare and integrate the check into your hook manager"
            )
    if action == "update" and not payload.exists():
        raise SetupError("Security payload is not installed; use install or prepare first")
    if payload.exists() or payload.is_symlink():
        metadata(payload)
    source = SOURCE.read_bytes()
    payload.mkdir(exist_ok=True)
    atomic_write(payload / "check.py", source, 0o644)
    atomic_write(payload / "manifest.json", (json.dumps({"owner": OWNER, "sha256": fingerprint(source)}, indent=2) + "\n").encode(), 0o644)
    if action == "install":
        hook.parent.mkdir(exist_ok=True)
        # Exclusive creation also prevents overwriting a concurrently installed hook.
        for name in HOOK_NAMES:
            try:
                fd = os.open(hook.parent / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o755)
            except FileExistsError:
                raise SetupError("Another Git hook appeared; it was preserved. Check setup status") from None
            with os.fdopen(fd, "wb") as stream:
                stream.write(HOOK.read_bytes())
                os.fchmod(stream.fileno(), 0o755)
    if action == "update" and not hooks_path_set(cwd):
        # Replace only exact earlier HQ copies; hand-edited or foreign hooks stay for status to report.
        for name in HOOK_NAMES:
            candidate = hook.parent / name
            if hook_version(candidate) == "previous":
                atomic_write(candidate, HOOK.read_bytes(), 0o755)
    print(f"OK: {action}; status={status(cwd)}")
    if action == "prepare":
        print('Integrate into the existing hook, preserving its failures:')
        print('python3 "$(git rev-parse --git-common-dir)/hq-commit-security/check.py" || exit $?')
        print("Manual integration must be verified with a failing test commit in an isolated repository")


def uninstall(cwd):
    _, payload, hook = locations(cwd)
    metadata(payload)
    if hook.parent.is_symlink():
        raise SetupError("External Git hooks directory preserved; remove HQ integration manually")
    for name in HOOK_NAMES:
        candidate = hook.parent / name
        if candidate.is_symlink() or (candidate.exists() and hook_version(candidate) is None):
            raise SetupError("Existing Git hook preserved; remove HQ integration manually")
    # External hook managers may still call this copy; do not silently remove it.
    if hooks_path_set(cwd):
        raise SetupError("External hook configuration preserved; remove integration before deleting the payload")
    if set(item.name for item in payload.iterdir()) != {"check.py", "manifest.json"}:
        raise SetupError("Extra payload files preserved; review them before removal")
    for name in HOOK_NAMES:
        candidate = hook.parent / name
        if candidate.exists():
            candidate.unlink()
    for name in ("check.py", "manifest.json"):
        (payload / name).unlink()
    payload.rmdir()
    print("OK: HQ Git hook and copied scanner removed")
    # Steps are repository-owned, so they are kept; without the HQ hook nothing runs them.
    for name in HOOK_NAMES:
        if (hook.parent / f"{name}.d").exists():
            print(f"Kept {name}.d/; its steps no longer run")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "prepare", "update", "status", "uninstall"))
    parser.add_argument("--repo", default=".")
    args = parser.parse_args()
    try:
        if args.action == "status":
            state = status(args.repo)
            print(state)
            return 0 if state == "ready" else 1
        if args.action == "uninstall":
            uninstall(args.repo)
        else:
            setup(args.repo, args.action)
        return 0
    except SetupError as error:
        # SetupError messages are static; never include raw OS/Git diagnostics.
        print(f"Setup stopped: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("Setup stopped: file operation failed; check status and the setup guide", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
