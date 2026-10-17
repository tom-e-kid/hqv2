#!/usr/bin/env python3
"""Report Git guard health at session start without modifying the repository."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from setup_security import SetupError, status


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
        except SetupError:
            # A session may start outside a Git working tree.
            return 0
        if state == "ready":
            return 0
        message = (
            f"HQ commit security: {state}. "
            "コミット前チェックの導入状態を確認してください。HQ の git Skill と docs/commit-security.md に導入・更新手順があります。"
            "Plugin の読み込みだけでは Git Hook を有効化しません。"
        )
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": message}}, ensure_ascii=False))
        return 0
    except (ValueError, AttributeError, OSError):
        print("HQ commit security: status check incomplete", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
