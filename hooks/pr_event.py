"""Shared detection of pull request creation in tool hook events for both clients."""

import json
import re


def tool_arguments(event):
    arguments = event.get('tool_input', {})
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return {}
    return arguments if isinstance(arguments, dict) else {}


def tool_command(event):
    arguments = tool_arguments(event)
    command = arguments.get('command', arguments.get('cmd', ''))
    return command if isinstance(command, str) else ''


def creation_candidate(event):
    name = event.get('tool_name', '')
    return bool(re.search(r'\bgh\s+pr\s+create\b', tool_command(event))) or bool(re.search(r'(?:create_pull_request|pull_request_create)$', name))
