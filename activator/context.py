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
   - Recent 3 rounds of notebook entries
   - Inspiration message (if any)
   - Wake-up signal

This design keeps the agent's context bounded and predictable.
The persona prompt defines the agent's personality and motivation,
while the appended rules ensure consistent tool usage.
"""

import os
from datetime import datetime, timezone
from activator.memory import MemoryManager


# =============================================================================
# Tool Documentation (appended to system message)
# =============================================================================

TOOL_DOCS = """
---

## Available Tools

You have 5 tools at your disposal:

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
Read your note from a specific past round. Your most recent 3 rounds are
already shown to you. Use this tool to look up older rounds.

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


def build_system_message(project_dir: str, persona_name: str) -> str:
    """
    Build the full system message: persona + tool docs + rules.

    The system message is static for the duration of a round.
    It defines who the agent is and what tools it can use.

    Args:
        project_dir:  Awakener project root.
        persona_name: Active persona name.

    Returns:
        Complete system message string.
    """
    persona = load_persona(project_dir, persona_name)
    return f"{persona}\n\n{TOOL_DOCS}"


def build_user_message(
    round_num: int,
    max_tool_calls: int,
    memory: MemoryManager,
    inject_count: int = 3,
) -> str:
    """
    Build the user message with contextual information.

    This message is sent at the start of each round and contains:
    - Current UTC time and round number
    - Tool budget for this round
    - Recent notebook entries (last N rounds)
    - Inspiration from admin (if any)
    - Wake-up signal

    Args:
        round_num:      Current activation round number.
        max_tool_calls: Tool budget for this round.
        memory:         MemoryManager instance.
        inject_count:   Number of recent notebook entries to inject.

    Returns:
        Complete user message string.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    parts = []

    # Header
    parts.append(f"Current time: {now}")
    parts.append(f"Round {round_num} (tool budget: {max_tool_calls})")
    parts.append("")

    # Recent notebook entries
    recent_notes = memory.get_recent_notes(count=inject_count)
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
