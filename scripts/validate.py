#!/usr/bin/env python3
"""Validate shared plugin identity, local sources, packaged resources and links."""

import argparse
import json
import re
from datetime import date
from pathlib import Path, PurePosixPath

import wip

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(relative):
    path = ROOT / relative
    data = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), f"{relative}: expected an object")
    return data


def contained_path(base, relative):
    path = (base / relative).resolve()
    require(path.is_relative_to(ROOT), f"Path escapes repository: {relative}")
    require(path.exists(), f"Missing resource: {path.relative_to(ROOT)}")
    return path


def validate_release_settings(settings, relative, check_files=False):
    release = settings.get("release")
    require(isinstance(release, dict), f"{relative}: missing release settings")
    for field in ("developmentBranch", "releaseBranch", "changelog"):
        value = release.get(field)
        require(isinstance(value, str) and value.strip(), f"{relative}: invalid {field}")
    require(isinstance(release.get("tagPrefix"), str), f"{relative}: invalid tagPrefix")
    files = release.get("versionFiles")
    require(isinstance(files, list), f"{relative}: versionFiles must be an array")
    for value in [release["changelog"], *files]:
        require(isinstance(value, str) and value.strip(), f"{relative}: invalid file path")
        require(not Path(value).is_absolute() and ".." not in Path(value).parts, f"{relative}: expected a repository-relative path")
        if check_files:
            require(contained_path(ROOT, value).is_file(), f"{relative}: expected a file: {value}")
    return release


def validate_release_ready(release, version):
    changelog = (ROOT / release["changelog"]).read_text(encoding="utf-8")
    unreleased = re.search(r"^## \[Unreleased\]\s*\n(.*?)(?=^## |\Z)", changelog, re.M | re.S)
    require(unreleased is not None, "Missing Unreleased section")
    require(not unreleased[1].strip(), "Unreleased must be empty when finalizing a release")
    section = re.search(rf"^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})\s*\n(.*?)(?=^## |\Z)", changelog, re.M | re.S)
    require(section is not None, f"Missing dated CHANGELOG section for {version}")
    date.fromisoformat(section[1])
    require(section[2].strip(), f"Empty CHANGELOG section for {version}")


def validate_plugin_hooks(codex, claude):
    require(codex.get("hooks") == "./hooks/codex.json", "Codex must reference its bundled hooks file")
    require(claude.get("hooks", "./hooks/hooks.json") == "./hooks/hooks.json", "Unexpected Claude hook path")
    for relative in ("hooks/codex.json", "hooks/hooks.json"):
        validate_hook_file(relative)


def validate_hook_file(relative):
    events = read_json(relative).get("hooks")
    require(isinstance(events, dict) and events.get("SessionStart"), "Missing SessionStart hook")
    for groups in events.values():
        require(isinstance(groups, list), "Hook event must contain an array")
        for group in groups:
            require(isinstance(group, dict) and isinstance(group.get("hooks"), list), "Invalid hook group")
            for hook in group["hooks"]:
                require(isinstance(hook, dict) and hook.get("type") == "command", "Expected a command hook")
                command = hook.get("command", "")
                require(isinstance(command, str), "Invalid hook command")
                resources = re.findall(r'\$\{(?:CLAUDE_PLUGIN_ROOT|PLUGIN_ROOT)\}/([^\s\"]+)', command)
                require(resources, "Hook command must reference a bundled resource")
                for resource in resources:
                    require(contained_path(ROOT, resource).is_file(), "Hook command resource must be a file")


def main(release_ready=False):
    codex = read_json(".codex-plugin/plugin.json")
    claude = read_json(".claude-plugin/plugin.json")
    for field in ("name", "version", "description"):
        require(codex.get(field), f"Missing Codex {field}")
        require(codex.get(field) == claude.get(field), f"Plugin {field} differs")
    require(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", codex["name"]), "Invalid plugin name")
    require(re.fullmatch(r"\d+\.\d+\.\d+", codex["version"]), "Invalid release version")
    validate_plugin_hooks(codex, claude)
    skill_dir = contained_path(ROOT, codex["skills"])
    require(skill_dir.is_dir(), "Codex skills path must be a directory")

    catalogs = [
        read_json(".agents/plugins/marketplace.json"),
        read_json(".claude-plugin/marketplace.json"),
    ]
    require(catalogs[0]["name"] == catalogs[1]["name"], "Marketplace names differ")
    for catalog in catalogs:
        matches = [entry for entry in catalog["plugins"] if entry["name"] == codex["name"]]
        require(len(matches) == 1, "Expected one matching plugin per marketplace")
        source = matches[0]["source"]
        if isinstance(source, dict):
            require(source["source"] == "local", "Expected a local Codex source")
            source = source["path"]
        require(contained_path(ROOT, source) == ROOT, "Marketplace must reference the plugin root")

    skills = list(skill_dir.glob("*/SKILL.md"))
    require(skills, "No skills found")
    for path in skills:
        body = path.read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---\n", body, re.S)
        require(match, f"Missing frontmatter: {path}")
        # Check shared identity; use a YAML parser for full frontmatter syntax validation.
        name = re.search(r"^name: ([a-z0-9-]+)$", match[1], re.M)
        description = re.search(r"^description: (.+)$", match[1], re.M)
        require(name and name[1] == path.parent.name, f"Skill name differs from directory: {path}")
        require(description and description[1].strip(), f"Missing skill description: {path}")

    for relative in (
        "hooks/hooks.json",
        "hooks/codex.json",
        "hooks/pr_feedback.py",
        "scripts/pr_feedback.py",
        "tests/test_pr_feedback.py",
        "skills/pr-feedback/references/operations.md",
        "skills/pr-feedback/SKILL.md",
        "examples/project/.hq/v2/pr-feedback.json",
        "hooks/security_status.py",
        "hooks/git/pre-commit",
        "scripts/commit_security.py",
        "scripts/setup_security.py",
        "tests/test_commit_security.py",
        "docs/references/commit-security.md",
        "skills/sdd/references/kickoff.md",
        "skills/sdd/references/direction-review.md",
        "skills/sdd/references/document-rules.md",
        "skills/sdd/references/document-roles.md",
        "skills/sdd/assets/docs/PRD.md",
        "skills/sdd/assets/docs/FDS.md",
        "skills/sdd/assets/docs/ADD.md",
        "skills/wip/SKILL.md",
        "skills/wip/assets/wip/requirements.md",
        "skills/wip/assets/wip/design.md",
        "skills/wip/assets/wip/tasks.md",
        "skills/wip/assets/wip/status.json",
        "skills/sweep/SKILL.md",
        "scripts/wip.py",
        "hooks/ssot_check.py",
        "hooks/pr_preflight.py",
        "hooks/pr_shell.py",
        "docs/references/pr-preflight.md",
        "docs/references/ssot.md",
        "hooks/pr_event.py",
        "docs/references/work-records.md",
        "skills/gotchas/SKILL.md",
        "skills/git/SKILL.md",
        "skills/git/references/settings.md",
        "skills/release/SKILL.md",
        "skills/release/references/settings.md",
        "skills/pr/SKILL.md",
        "skills/pr/assets/pr-body.md",
        "CHANGELOG.md",
        ".hq/v2/git.md",
        ".hq/v2/release.md",
        ".hq/v2/settings.json",
        "examples/project/AGENTS.md",
        "examples/project/CLAUDE.md",
        "examples/project/.gitignore",
        "examples/project/.hq/v2/git.md",
        "examples/project/.hq/v2/settings.json",
        "examples/project/.hq/v2/settings.local.example.json",
        "examples/project/.hq/v2/release.md",
        "examples/project/.hq/v2/pr.md",
    ):
        contained_path(ROOT, relative)

    for relative in (
        ".hq/v2/settings.json",
        "examples/project/.hq/v2/settings.json",
        "examples/project/.hq/v2/settings.local.example.json",
    ):
        settings = read_json(relative)
        git = settings.get("git")
        require(isinstance(git, dict), f"{relative}: missing git settings")
        for field in ("remote", "baseBranch"):
            if field in git:
                require(isinstance(git[field], str) and git[field].strip(), f"{relative}: invalid {field}")
        branches = git.get("branches", {})
        require(isinstance(branches, dict), f"{relative}: branches must be an object")
        for branch, target in branches.items():
            require(isinstance(branch, str) and branch.strip(), f"{relative}: invalid branch key")
            require(isinstance(target, dict), f"{relative}: invalid target for {branch}")
            for field in ("remote", "baseBranch"):
                value = target.get(field)
                require(isinstance(value, str) and value.strip(), f"{relative}: missing {field} for {branch}")
        if "commitSecurity" in settings:
            section = settings["commitSecurity"]
            require(isinstance(section, dict) and isinstance(section.get("required"), bool), f"{relative}: commitSecurity.required must be a boolean")
        for key in ("wip", "gotchas", "sdd"):
            if key in settings:
                section = settings[key]
                value = section.get("path") if isinstance(section, dict) else None
                require(isinstance(value, str) and value.strip() == value and value, f"{relative}: {key}.path must be a non-empty string")
                path = PurePosixPath(value)
                require(not path.is_absolute() and ".." not in path.parts, f"{relative}: {key}.path must stay inside the repository")
        if isinstance(settings.get("wip"), dict) and "prPreflight" in settings["wip"]:
            require(isinstance(settings["wip"]["prPreflight"], bool), f"{relative}: wip.prPreflight must be a boolean")
        if "ssot" in settings:
            # The SSOT is registered explicitly; the repository root would cover the implementation too.
            section = settings["ssot"]
            values = section.get("paths") if isinstance(section, dict) else None
            require(isinstance(values, list) and values, f"{relative}: ssot.paths must be a non-empty list")
            for value in values:
                require(isinstance(value, str) and value.strip() == value and value, f"{relative}: ssot.paths entries must be non-empty strings")
                path = PurePosixPath(value)
                require(not path.is_absolute() and ".." not in path.parts and path != PurePosixPath("."),
                        f"{relative}: ssot.paths entries must stay inside the repository and must not be its root")

    # This repository keeps its own work records; each needs a valid status file.
    for record in wip.records(ROOT):
        require(record["problem"] is None, f"{record['path']}: {record['problem']}")
    template, problem = wip.parse_status((ROOT / "skills/wip/assets/wip/status.json").read_text(encoding="utf-8"))
    require(problem is None, f"skills/wip/assets/wip/status.json: {problem}")

    settings = read_json(".hq/v2/settings.json")
    release = validate_release_settings(settings, ".hq/v2/settings.json", check_files=True)
    require(settings["git"].get("baseBranch") == release["developmentBranch"], "Git default base differs from development branch")
    expected_version_files = {".codex-plugin/plugin.json", ".claude-plugin/plugin.json"}
    require(expected_version_files.issubset(release["versionFiles"]), "Release versionFiles must include both plugin manifests")
    validate_release_settings(read_json("examples/project/.hq/v2/settings.json"), "examples/project/.hq/v2/settings.json")
    if release_ready:
        validate_release_ready(release, codex["version"])

    link_count = 0
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts or path.is_relative_to(ROOT / "work"):
            continue
        body = path.read_text(encoding="utf-8")
        for target in re.findall(r"\[[^\]]+\]\(([^\s)]+)\)", body):
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                continue
            contained_path(path.parent, target.split("#", 1)[0])
            link_count += 1
        for imported in re.findall(r"^@([^\s]+\.md)$", body, re.M):
            contained_path(path.parent, imported)

    print(f"OK: {codex['name']} {codex['version']}, {len(skills)} shared skill(s), two marketplaces, {link_count} local links")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true", help="also check the finalized CHANGELOG for the current version")
    args = parser.parse_args()
    try:
        main(release_ready=args.release)
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Validation failed: {error}")
