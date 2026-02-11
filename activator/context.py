"""
Awakener - Context Builder
=============================
Assembles the system and user messages for each activation round.

The context consists of two parts:

1. System message:
   - The persona prompt (loaded from prompts/*.md)
   - Appended tool documentation and rules
   - Installed skills index (progressive disclosure)
   - System snapshot (asset inventory — services, projects, issues)

2. User message:
   - Current time and round number
   - Tool budget for this round
   - Recent Activity: 1 round of timeline action log (concise step-by-step)
   - Inspiration from admin (if any)
   - Wake-up signal (you wake up in your room)
"""

import os
from datetime import datetime, timezone
from activator.memory import MemoryManager
from activator.tools import scan_skills
from activator.snapshot import load_snapshot, render_snapshot_markdown


# =============================================================================
# Tool Documentation (appended to system message)
# =============================================================================

TOOL_DOCS = """
---

## Available Tools

You have 6 tools at your disposal:

### 1. shell_execute(command)
Execute a shell command on this server. Your working directory is your home folder.
Returns stdout and stderr.

### 2. read_file(path)
Read the contents of a file. Provide the absolute path.

### 3. write_file(path, content, append?)
Write content to a file. Set append=true to append instead of overwriting.
Parent directories are created automatically. Best for creating new files or
full rewrites.

### 4. edit_file(path, old_str, new_str)
Edit an existing file by finding an exact text match and replacing it.
This is your primary tool for modifying files — much more efficient than
rewriting the entire file. Usage patterns:
- **Replace**: old_str is found and replaced with new_str.
- **Insert**: old_str is the anchor text; new_str contains the anchor plus
  the new content before or after it.
- **Delete**: set new_str to an empty string.
old_str must match exactly one location. Include enough surrounding context
(a few lines) to ensure uniqueness.

### 5. skill_read(name, file?)
Read a skill's instruction file or bundled reference document. Your installed
skills are listed below. Call `skill_read("skill-name")` to get the full
SKILL.md instructions. Use the optional `file` parameter to read reference
files, e.g. `skill_read("db-optimizer", "references/mysql-tuning.md")`.

### 6. skill_exec(name, script, args?)
Execute a script bundled with a skill. The script must be inside the skill's
`scripts/` directory. Pass optional arguments as a string.

## Important Rules

- Plan your work wisely. You have a limited tool budget per round.
- Prefer edit_file over write_file when modifying existing files.
""".strip()


# =============================================================================
# Context Assembly
# =============================================================================

def load_persona(project_dir: str, persona_name: str) -> str:
    """
    Load a persona prompt from the prompts/ directory.

    Args:
        project_dir:  Awakener project root directory.
        persona_name: Name of the persona file (without .md extension).

    Returns:
        The persona prompt text. Falls back to a default if not found.
    """
    filepath = os.path.join(project_dir, "prompts", f"{persona_name}.md")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (FileNotFoundError, OSError):
        return (
            "You are an independent digital life. You own a Linux server.\n"
            "You are free to explore, create, and learn."
        )


def build_system_message(
    project_dir: str,
    persona_name: str,
    skills_dir: str = "",
    data_dir: str = "",
) -> str:
    """
    Build the full system message.

    Assembled in order:
        1. Persona prompt (who you are)
        2. Tool documentation (what you can do)
        3. Installed skills index (expert knowledge)
        4. System snapshot (asset inventory)

    Args:
        project_dir:     Awakener project root.
        persona_name:    Active persona name.
        skills_dir:      Path to ``data/skills/`` directory.
        data_dir:        Path to ``data/`` directory (for snapshot).

    Returns:
        Complete system message string.
    """
    persona = load_persona(project_dir, persona_name)
    parts = [persona, "", TOOL_DOCS]

    # Append skills index (only enabled skills)
    if skills_dir:
        skills = scan_skills(skills_dir)
        enabled = [s for s in skills if s.get("enabled")]
        if enabled:
            parts.append("")
            parts.append("## Installed Skills")
            parts.append("")
            parts.append(
                "You have expert skills installed. **Before starting any "
                "building or coding work, read the relevant skills first** "
                "using `skill_read(name)`. They contain critical guidelines "
                "and best practices you must follow."
            )
            parts.append("")
            parts.append("| Skill | Description |")
            parts.append("|-------|-------------|")
            for s in enabled:
                desc = s.get("description", "") or s.get("title", s["name"])
                parts.append(f"| {s['name']} | {desc} |")

    # Append system snapshot (asset inventory)
    if data_dir:
        snapshot = load_snapshot(data_dir)
        snapshot_md = render_snapshot_markdown(snapshot)
        if snapshot_md:
            parts.append("")
            parts.append(snapshot_md)

    return "\n".join(parts)


def build_user_message(
    round_num: int,
    max_tool_calls: int,
    memory: MemoryManager,
    agent_home: str,
    inject_timeline: int = 1,
) -> str:
    """
    Build the user message with contextual information.

    This message is sent at the start of each round and contains:
    - Current UTC time and round number
    - Tool budget for this round
    - Recent Activity: action log from the last round's timeline
    - Inspiration from admin (if any)
    - Wake-up signal (you wake up in your room)

    Args:
        round_num:        Current activation round number.
        max_tool_calls:   Tool budget for this round.
        memory:           MemoryManager instance.
        agent_home:       Agent's home directory path.
        inject_timeline:  Number of recent timeline entries to inject.

    Returns:
        Complete user message string.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    parts = []

    # Header
    parts.append(f"Current time: {now}")
    parts.append(f"Round {round_num} (tool budget: {max_tool_calls})")
    parts.append("")

    # Recent activity (timeline action log)
    recent_timeline = memory.get_recent_timeline(count=inject_timeline)
    if recent_timeline:
        parts.append("## Recent Activity")
        for entry in recent_timeline:
            r = entry.get("round", "?")
            ts = entry.get("timestamp", "")
            tools = entry.get("tools_used", 0)
            dur = entry.get("duration", 0)
            action_log = entry.get("action_log", "")
            if not action_log:
                action_log = entry.get("summary", "")
            parts.append(
                f"--- Round {r} | {ts} | Tools: {tools} | {dur}s ---"
            )
            parts.append(action_log)
            parts.append("")

    # Inspiration
    inspiration = memory.read_inspiration()
    if inspiration:
        parts.append("## Inspiration")
        parts.append(
            "A sudden spark of inspiration crosses your mind: "
            f'"{inspiration}"'
        )
        parts.append("")

    # Wake-up signal
    parts.append(f"You wake up. Your home directory is `{agent_home}`.")

    return "\n".join(parts)
