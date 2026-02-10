"""
Awakener - Context Builder
=============================
Assembles the system and user messages for each activation round.

The context consists of two parts:

1. System message:
   - The persona prompt (loaded from prompts/*.md)
   - Appended tool documentation and rules

2. User message:
   - Current time and round number
   - Tool budget for this round
   - Recent Activity: 1 round of timeline action log (concise step-by-step)
   - Your Recent Notes: 1 round of notebook (detailed plan & status)
   - Inspiration from admin (if any)
   - Wake-up signal

The "action log + notebook" combination gives the agent two complementary
perspectives on its recent history:
  - Action log: *what it did* (objective, timestamped tool-calling steps)
  - Notebook: *what it learned and plans* (subjective, structured notes)

This replaces the previous 3-round-notebook injection, saving tokens while
providing better continuity.
"""

import os
from datetime import datetime, timezone
from activator.memory import MemoryManager
from activator.tools import scan_skills


# =============================================================================
# Tool Documentation (appended to system message)
# =============================================================================

TOOL_DOCS = """
---

## Available Tools

You have 7 tools at your disposal:

### 1. shell_execute(command)
Execute a shell command on this server. Your working directory is your home folder.
Returns stdout and stderr.

### 2. read_file(path)
Read the contents of a file. Provide the absolute path.

### 3. write_file(path, content, append?)
Write content to a file. Set append=true to append instead of overwriting.
Parent directories are created automatically.

### 4. notebook_write(content)
Save your note for this activation round. Write down what you did, what you
learned, and what you plan to do next. **You MUST call this at least once
before the round ends.**

### 5. notebook_read(round)
Read your note from a specific past round. Your most recent rounds are
already shown to you. Use this tool to look up older rounds.

### 6. skill_read(name, file?)
Read a skill's instruction file or bundled reference document. Your installed
skills are listed below. Call `skill_read("skill-name")` to get the full
SKILL.md instructions. Use the optional `file` parameter to read reference
files, e.g. `skill_read("db-optimizer", "references/mysql-tuning.md")`.

### 7. skill_exec(name, script, args?)
Execute a script bundled with a skill. The script must be inside the skill's
`scripts/` directory. Pass optional arguments as a string.

## Important Rules

- You MUST call `notebook_write` before the round ends. This is your persistent
  memory. Without it, you will forget everything from this round.
- Plan your work wisely. You have a limited tool budget per round.
- If a task takes multiple rounds, record detailed progress in your notebook
  so you can continue seamlessly next time.
- There is a restricted zone on this server that you cannot access.
  If you encounter a "[BLOCKED]" message, that area is off-limits.
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
) -> str:
    """
    Build the full system message: persona + tool docs + skills index.

    The system message is static for the duration of a round.
    It defines who the agent is, what tools it can use, and which
    skills are available.

    Skills are presented as a concise index table. The agent must call
    ``skill_read(name)`` to get the full instructions (progressive
    disclosure — saves tokens when skills are not needed this round).

    Args:
        project_dir:  Awakener project root.
        persona_name: Active persona name.
        skills_dir:   Path to ``data/skills/`` directory.

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
                "The following skills are available. Use `skill_read(name)` "
                "to read full instructions when you need to apply a skill."
            )
            parts.append("")
            parts.append("| Skill | Description |")
            parts.append("|-------|-------------|")
            for s in enabled:
                desc = s.get("description", "") or s.get("title", s["name"])
                parts.append(f"| {s['name']} | {desc} |")

    return "\n".join(parts)


def build_user_message(
    round_num: int,
    max_tool_calls: int,
    memory: MemoryManager,
    inject_timeline: int = 1,
    inject_notes: int = 1,
) -> str:
    """
    Build the user message with contextual information.

    This message is sent at the start of each round and contains:
    - Current UTC time and round number
    - Tool budget for this round
    - Recent Activity: action log from the last round's timeline
    - Your Recent Notes: the latest notebook entry
    - Inspiration from admin (if any)
    - Wake-up signal

    The action-log + notebook combination replaces the old 3-round-notebook
    injection. It provides better continuity with fewer tokens:
    - Action log shows *what the agent did* (timestamped steps)
    - Notebook shows *what the agent learned and plans next*

    Args:
        round_num:        Current activation round number.
        max_tool_calls:   Tool budget for this round.
        memory:           MemoryManager instance.
        inject_timeline:  Number of recent timeline entries to inject.
        inject_notes:     Number of recent notebook entries to inject.

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
            # Prefer the concise action_log; fall back to full summary
            # for legacy entries that don't have the action_log field.
            action_log = entry.get("action_log", "")
            if not action_log:
                action_log = entry.get("summary", "")
            parts.append(
                f"--- Round {r} | {ts} | Tools: {tools} | {dur}s ---"
            )
            parts.append(action_log)
            parts.append("")

    # Recent notebook entries
    recent_notes = memory.get_recent_notes(count=inject_notes)
    if recent_notes:
        parts.append("## Your Recent Notes")
        for note in recent_notes:
            r = note.get("round", "?")
            ts = note.get("timestamp", "")
            content = note.get("content", "")
            parts.append(f"--- Round {r} | {ts} ---")
            parts.append(content)
            parts.append("")
    else:
        parts.append("## Your Recent Notes")
        parts.append("(No previous notes. This appears to be your first activation.)")
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
    parts.append("You wake up.")

    return "\n".join(parts)
