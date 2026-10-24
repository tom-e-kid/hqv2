#!/usr/bin/env python3
"""Report Git guard health at session start without modifying the repository."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from setup_security import SetupError, locations, status

# Checkout-local settings override the shared ones, as for the other HQ settings.
SETTINGS = (".hq/v2/.ignore/settings.json", ".hq/v2/settings.json")
GUIDE = "HQ の git Skill と docs/references/commit-security.md に導入・更新・解除の手順があります。Plugin の読み込みだけでは Git Hook を有効化しません。"


def required(root):
    """Return commitSecurity.required; raise ValueError for a malformed declaration."""
    for relative in SETTINGS:
        path = root / relative
        if not path.is_file():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(relative)
        if "commitSecurity" not in data:
            continue
        section = data["commitSecurity"]
        if not isinstance(section, dict) or not isinstance(section.get("required"), bool):
            raise ValueError(relative)
        return section["required"]
    return False


def main():
    try:
        event = json.load(sys.stdin)
        if event.get("hook_event_name") != "SessionStart":
            return 0
        cwd = event.get("cwd")
        if not isinstance(cwd, str) or not cwd:
            return 0
        try:
            state = status(cwd)
            root = locations(cwd)[0] if state == "not-installed" else None
        except SetupError:
            # A session may start outside a Git working tree.
            return 0
        if state == "ready":
            return 0
        if state == "not-installed":
            # Not installing is a valid choice; only repositories that declared adoption are reminded.
            try:
                if not required(root):
                    return 0
                message = f"HQ commit security: {state}. このリポジトリの設定 commitSecurity.required が導入を求めています。{GUIDE}"
            except (OSError, ValueError):
                message = (
                    f"HQ commit security: {state}. .hq/v2/settings.json または .hq/v2/.ignore/settings.json の "
                    'commitSecurity を読み取れません。{"required": true} または false の形式か確認してください。'
                )
        else:
            message = f"HQ commit security: {state}. コミット前チェックの導入状態を確認してください。{GUIDE}"
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": message}}, ensure_ascii=False))
        return 0
    except (ValueError, AttributeError, OSError):
        print("HQ commit security: status check incomplete", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
