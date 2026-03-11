"""
Awakener - Skill Management Service
=======================================
Scans, parses, and manages installed skills.
Used by both the context builder and the web API.
"""

import json
import os
import yaml


def _load_skills_config(skills_dir: str) -> dict:
    """Load the skills enabled/disabled state from ``_config.json``."""
    config_path = os.path.join(skills_dir, "_config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {"disabled": []}


def _save_skills_config(skills_dir: str, config: dict) -> None:
    """Save the skills configuration to ``_config.json``."""
    config_path = os.path.join(skills_dir, "_config.json")
    os.makedirs(skills_dir, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def scan_skills(skills_dir: str) -> list[dict]:
    """
    Scan the skills directory and return metadata for all installed skills.

    Each skill is a subdirectory containing a ``SKILL.md`` file with
    optional YAML frontmatter.
    """
    if not os.path.isdir(skills_dir):
        return []

    config = _load_skills_config(skills_dir)
    disabled = set(config.get("disabled", []))
    skills = []

    for entry in sorted(os.listdir(skills_dir)):
        if entry.startswith("_") or entry.startswith("."):
            continue
        skill_path = os.path.join(skills_dir, entry)
        if not os.path.isdir(skill_path):
            continue

        skill_md = os.path.join(skill_path, "SKILL.md")
        if not os.path.isfile(skill_md):
            continue

        meta = _parse_skill_frontmatter(skill_md)

        skills.append({
            "name": entry,
            "title": meta.get("name", entry),
            "description": meta.get("description", ""),
            "version": str(meta.get("version", "")),
            "tags": meta.get("tags", []),
            "enabled": entry not in disabled,
            "has_scripts": os.path.isdir(os.path.join(skill_path, "scripts")),
            "has_refs": os.path.isdir(os.path.join(skill_path, "references")),
        })

    return skills


def _parse_skill_frontmatter(filepath: str) -> dict:
    """Parse YAML frontmatter from a SKILL.md file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return {}

    if not content.startswith("---"):
        return {}

    end = content.find("---", 3)
    if end == -1:
        return {}

    frontmatter = content[3:end].strip()
    try:
        return yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError:
        return {}
