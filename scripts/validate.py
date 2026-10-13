#!/usr/bin/env python3
"""Validate shared plugin identity, local sources, packaged resources and links."""

import json
import re
from pathlib import Path

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


def main():
    codex = read_json(".codex-plugin/plugin.json")
    claude = read_json(".claude-plugin/plugin.json")
    for field in ("name", "version", "description"):
        require(codex.get(field), f"Missing Codex {field}")
        require(codex.get(field) == claude.get(field), f"Plugin {field} differs")
    require(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", codex["name"]), "Invalid plugin name")
    require(re.fullmatch(r"\d+\.\d+\.\d+", codex["version"]), "Invalid release version")
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
        "skills/sdd/references/kickoff.md",
        "skills/sdd/references/change-workflow.md",
        "skills/sdd/references/document-rules.md",
        "skills/sdd/assets/docs/PRD.md",
        "skills/sdd/assets/docs/FDS.md",
        "skills/sdd/assets/docs/ADD.md",
        "skills/steering/SKILL.md",
        "skills/steering/assets/steering/requirements.md",
        "skills/steering/assets/steering/design.md",
        "skills/steering/assets/steering/tasks.md",
        "examples/project/AGENTS.md",
        "examples/project/CLAUDE.md",
    ):
        contained_path(ROOT, relative)

    link_count = 0
    for path in ROOT.rglob("*.md"):
        if ".git" in path.parts or "work" in path.parts:
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
    try:
        main()
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Validation failed: {error}")
