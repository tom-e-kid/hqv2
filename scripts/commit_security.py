#!/usr/bin/env python3
"""Check staged files for local paths, environment files and likely credentials."""

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

POLICY_PATH = ".hq/v2/security.json"
MAX_BYTES = 10 * 1024 * 1024
RULES = {"env-file", "local-path", "private-key", "service-token", "secret-assignment", "unscannable"}

# Prefixes are intentionally limited: this is a baseline guard, not a secret inventory.
SERVICE_TOKEN = re.compile(
    r"(?<![\w-])(?:"
    r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})|"
    r"sk-(?:(?:proj|svcacct)-)?[A-Za-z0-9_-]{20,}|"
    r"(?:AKIA|ASIA)[A-Z0-9]{16}|"
    r"AIza[A-Za-z0-9_-]{35}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"(?:sk|rk)_live_[A-Za-z0-9]{16,}"
    r")(?![\w-])"
)
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----")
LOCAL_PATH = re.compile(
    r"(?:/(?:Users|home)/[\w.-]+(?:[ /\"'`]|$)|"
    r"/root/[A-Za-z0-9_.-]+|"
    r"/(?:private/)?var/folders/[A-Za-z0-9_-]+/|"
    r"[A-Za-z]:[\\/]{1,2}(?:Users|Documents and Settings)[\\/]{1,2}[A-Za-z0-9_.-]+(?:[\\/ \"']|$))"
)
ASSIGNMENT = re.compile(
    r'''(?i)(?<![\w.-])["']?(?:[A-Za-z0-9_.-]*[_\-.])?'''
    r'''(?:api[_-]?key|(?:access|auth|refresh|id)[_-]?token|token|'''
    r'''(?:client|api|aws)[_-]?secret|secret(?:[_-]?key)?|password|passwd|authorization)'''
    r'''["']?\s*(?:=|:)\s*("[^"\r\n]*"|'[^'\r\n]*'|[^\s,;#}\]]+)'''
)
PLACEHOLDER = re.compile(
    r"(?i)(?:<[^>]+>|\$\{[^}]+\}|\$[A-Z_][A-Z0-9_]*|\{\{.*\}\}|"
    r"(?:your|example|dummy|test|replace|placeholder)(?:[-_ ].*)?|"
    r"change[-_]?me|replace[-_]?me|none|null|true|false|[x*]+)"
)
# How secret-assignment reads values: "config" keeps bare values as literals; the others are code,
# where only quoted values are literals and a double-quoted value with interpolation is an expression.
# An odd run of backslashes escapes the next character, so only an even run may precede interpolation.
UNESCAPED = r"(?<!\\)(?:\\\\)*"
INTERPOLATION = {
    "config": None,
    "quoted": None,
    "swift": re.compile(UNESCAPED + r"\\\("),
    "kotlin": re.compile(UNESCAPED + r"\$(?:\{|[A-Za-z_])"),
    "ruby": re.compile(UNESCAPED + r"#\{"),
}
FILE_TYPES = {
    **dict.fromkeys((
        ".py", ".pyi", ".java", ".c", ".h", ".cc", ".cpp", ".cxx", ".hh", ".hpp", ".m", ".mm", ".go", ".rs", ".cs", ".scala",
        # JavaScript interpolates only in backtick strings, which are not read as quoted values.
        ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts",
    ), "quoted"),
    ".swift": "swift",
    **dict.fromkeys((".kt", ".kts", ".dart", ".groovy", ".gradle", ".php"), "kotlin"),
    ".rb": "ruby",
}
# Images, documents and fonts whose unscannable finding a repository may turn off.
BINARY_TYPES = dict.fromkeys((
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".heif", ".bmp", ".tif", ".tiff", ".ico", ".icns",
    ".pdf", ".ttf", ".otf", ".ttc", ".woff", ".woff2",
), True)


class CheckError(Exception):
    """A check could not be completed; messages never contain file contents."""


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    line: int
    fingerprint: str


@dataclass(frozen=True)
class Policy:
    allow: tuple = ()
    file_types: dict = field(default_factory=lambda: FILE_TYPES)
    binaries: bool = True
    binary_types: dict = field(default_factory=lambda: BINARY_TYPES)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_type(path, types):
    """Return the value of the longest key that ends the file name, compared case-insensitively."""
    name = path.rsplit("/", 1)[-1].lower()
    matches = [key for key in types if name.endswith(key)]
    return types[max(matches, key=len)] if matches else None


class Repository:
    def __init__(self, cwd):
        self.cwd = Path(cwd)
        self.env = os.environ.copy()
        # Git may supply an alternate index during commit -a / --only.
        for name in ("GIT_INDEX_FILE", "GIT_DIR", "GIT_COMMON_DIR", "GIT_WORK_TREE", "GIT_OBJECT_DIRECTORY"):
            if self.env.get(name) and not Path(self.env[name]).is_absolute():
                self.env[name] = str((self.cwd / self.env[name]).resolve())
        self.root = Path(os.fsdecode(self.git("rev-parse", "--show-toplevel")).rstrip("\n"))
        self.cwd = self.root

    def git(self, *args):
        result = subprocess.run(["git", *args], cwd=self.cwd, env=self.env, capture_output=True)
        if result.returncode:
            raise CheckError("Git read failed; security check incomplete")
        return result.stdout

    def entries(self):
        entries = {}
        for item in self.git("ls-files", "--stage", "--full-name", "-z").split(b"\0"):
            if not item:
                continue
            header, path = item.split(b"\t", 1)
            mode, oid, stage = header.decode("ascii").split()
            if stage != "0":
                raise CheckError("Unmerged index; security check incomplete")
            entries[os.fsdecode(path)] = (mode, oid)
        return entries

    def blob(self, oid, limit=MAX_BYTES):
        size = int(self.git("cat-file", "-s", oid))
        if size > limit:
            return None
        return self.git("cat-file", "blob", oid)


def file_type_overrides(defaults, overrides, valid):
    """Merge per-extension overrides; keys are file-name suffixes such as ".swift" or ".gradle.kts"."""
    if not isinstance(overrides, dict):
        raise ValueError
    merged = dict(defaults)
    seen = set()
    for key, value in overrides.items():
        key = key.lower()
        if key in seen or not re.fullmatch(r"(?:\.[a-z0-9][a-z0-9_+-]*)+", key) or not valid(value):
            raise ValueError
        seen.add(key)
        merged[key] = value
    return merged


def parse_policy(policy):
    if not isinstance(policy, dict) or not {"version", "allow"} <= set(policy) <= {"version", "allow", "rules"}:
        raise ValueError
    if type(policy["version"]) is not int or policy["version"] != 1 or not isinstance(policy["allow"], list):
        raise ValueError
    for entry in policy["allow"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "rule", "fingerprint", "reason"}:
            raise ValueError
        if not all(isinstance(value, str) and value.strip() for value in entry.values()):
            raise ValueError
        path = entry["path"]
        if path.startswith("/") or "\\" in path or any(part in {"", ".", ".."} for part in path.split("/")):
            raise ValueError
        if entry["rule"] not in RULES or not re.fullmatch(r"(?:sha256:[a-f0-9]{64}|blob:[a-f0-9]{40}|blob:[a-f0-9]{64})", entry["fingerprint"]):
            raise ValueError
    rules = policy.get("rules", {})
    if not isinstance(rules, dict) or not set(rules) <= {"secret-assignment", "unscannable"}:
        raise ValueError
    assignment = rules.get("secret-assignment", {})
    unscannable = rules.get("unscannable", {})
    if not isinstance(assignment, dict) or not set(assignment) <= {"fileTypes"}:
        raise ValueError
    if not isinstance(unscannable, dict) or not set(unscannable) <= {"binaries", "binaryTypes"}:
        raise ValueError
    binaries = unscannable.get("binaries", True)
    if type(binaries) is not bool:
        raise ValueError
    file_types = file_type_overrides(FILE_TYPES, assignment.get("fileTypes", {}), lambda value: value in INTERPOLATION)
    binary_types = file_type_overrides(BINARY_TYPES, unscannable.get("binaryTypes", {}), lambda value: type(value) is bool)
    return Policy(tuple(policy["allow"]), file_types, binaries, binary_types)


def load_policy(repo, entries):
    if POLICY_PATH not in entries:
        return Policy()
    mode, oid = entries[POLICY_PATH]
    if mode not in {"100644", "100755"}:
        raise CheckError("Security policy must be a regular staged file")
    try:
        data = repo.blob(oid, 1024 * 1024)
        if data is None:
            raise ValueError
        return parse_policy(json.loads(data))
    except (ValueError, TypeError, UnicodeError):
        raise CheckError("Invalid staged security policy; expected version 1 with explicit, reasoned exceptions and known rule settings") from None


def environment_file(path):
    name = path.rsplit("/", 1)[-1].lower()
    if name.endswith((".example", ".sample", ".template")):
        return False
    return bool(re.search(r"(?:^\.env(?:\.|$)|\.env(?:\.|$)|^\.envrc(?:\.|$))", name))


def concrete_assignment(line, style="config"):
    interpolation = INTERPOLATION[style]
    for match in ASSIGNMENT.finditer(line):
        raw = match[1]
        quoted = raw[:1] in {"'", '"'}
        value = raw[1:-1] if quoted else raw
        if len(value) < 8 or PLACEHOLDER.fullmatch(value):
            continue
        if style != "config":
            # In code, bare values are variables or types, and interpolation makes a string an expression.
            # Single quotes never interpolate here; Dart's single-quoted interpolation stays concrete (safe side).
            if not quoted or (raw[0] == '"' and interpolation and interpolation.search(value)):
                continue
        # Unquoted program expressions and variable references are not literal secrets.
        elif not quoted and (not re.fullmatch(r"[A-Za-z0-9_+/=:-]+", value) or re.fullmatch(r"[A-Z_][A-Z0-9_]*", value)):
            continue
        return True
    return False


def inspect_file(path, mode, oid, content, policy=Policy()):
    findings = []
    if environment_file(path):
        findings.append(Finding(path, "env-file", 0, "blob:" + oid))
    if mode == "160000" or content is None:
        findings.append(Finding(path, "unscannable", 0, "blob:" + oid))
        return findings
    try:
        text = content.decode("utf-16") if content.startswith((b"\xff\xfe", b"\xfe\xff")) else content.decode("utf-8-sig")
        if "\0" in text:
            raise UnicodeError
    except UnicodeError:
        # Still detect recognizable credentials in the printable parts of a binary.
        text = content.decode("utf-8", errors="replace")
        if policy.binaries or not file_type(path, policy.binary_types):
            findings.append(Finding(path, "unscannable", 0, "blob:" + oid))
    style = file_type(path, policy.file_types) or "config"
    for number, line in enumerate(text.splitlines(), 1):
        fingerprint = "sha256:" + digest(line.encode("utf-8"))
        for rule, pattern in (("local-path", LOCAL_PATH), ("private-key", PRIVATE_KEY), ("service-token", SERVICE_TOKEN)):
            if pattern.search(line):
                findings.append(Finding(path, rule, number, fingerprint))
        if concrete_assignment(line, style):
            findings.append(Finding(path, "secret-assignment", number, fingerprint))
    return findings


def check(cwd, fingerprints=False):
    repo = Repository(cwd)
    entries = repo.entries()
    policy = load_policy(repo, entries)
    paths = [os.fsdecode(path) for path in repo.git(
        "diff", "--cached", "--no-relative", "--no-ext-diff", "--no-textconv", "--name-only", "--no-renames", "--diff-filter=ACMTUXB", "-z", "--"
    ).split(b"\0") if path]
    found = []
    accepted = 0
    for path in paths:
        if path not in entries:
            raise CheckError("Staged entry missing; security check incomplete")
        mode, oid = entries[path]
        content = None if mode == "160000" else repo.blob(oid)
        for finding in inspect_file(path, mode, oid, content, policy):
            if any(entry["path"] == path and entry["rule"] == finding.rule and entry["fingerprint"] == finding.fingerprint for entry in policy.allow):
                accepted += 1
            else:
                found.append(finding)
    for finding in found:
        # JSON quoting prevents filenames from injecting terminal controls or extra lines.
        location = json.dumps(finding.path, ensure_ascii=True) + (f":{finding.line}" if finding.line else "")
        suffix = f" [{finding.fingerprint}]" if fingerprints else ""
        print(f"{location}: {finding.rule}{suffix}", file=sys.stderr)
    if found:
        print(f"BLOCKED: {len(found)} finding(s); staged contents need review", file=sys.stderr)
        return 1
    print(f"OK: commit security, {len(paths)} staged file(s), {accepted} explicit exception(s)")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository or a directory within it")
    parser.add_argument("--fingerprints", action="store_true", help="include content fingerprints for reviewed exceptions")
    args = parser.parse_args()
    try:
        return check(args.repo, args.fingerprints)
    except CheckError as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("BLOCKED: security check could not complete; check Git, index, and security policy", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
