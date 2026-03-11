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

2. Context messages (multi-turn format):
   - Historical rounds as user/assistant pairs (final output only)
   - Inspiration as a system message (if any)
   - Current round wake-up as user message
"""

import os
import json
from datetime import datetime, timezone

from services.memory import MemoryManager
from services.skills import scan_skills
from agents.auditor.snapshot import load_snapshot, render_snapshot_markdown, _extract_final_output


# =============================================================================
# Tool Documentation (appended to system message)
# =============================================================================

TOOL_DOCS_BASE = """
---

## Available Tools

You have {tool_count} tools at your disposal:

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
""".strip()

TOOL_DOCS_RULES = """
## Important Rules

- Plan your work wisely. You have a limited tool budget per round.
- Prefer edit_file over write_file when modifying existing files.
""".strip()


# =============================================================================
# Context Assembly
# =============================================================================

def load_persona(project_dir: str, persona_name: str = "persona") -> str:
    filepath = os.path.join(project_dir, "agents", "activator", f"{persona_name}.md")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (FileNotFoundError, OSError):
        return (
            "You are an independent digital life. You own a Linux server.\n"
            "You are free to explore, create, and learn."
        )


def load_rules(project_dir: str) -> str:
    filepath = os.path.join(project_dir, "agents", "activator", "rules.md")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (FileNotFoundError, OSError):
        return ""


def load_lessons(agent_home: str) -> str:
    filepath = os.path.join(agent_home, "LESSONS.md")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (FileNotFoundError, OSError):
        return ""


def load_memory_index(agent_home: str) -> str:
    filepath = os.path.join(agent_home, "memory", "INDEX.md")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read().strip()
    except (FileNotFoundError, OSError):
        return ""


def build_system_message(
    project_dir: str,
    persona_name: str,
    skills_dir: str = "",
    data_dir: str = "",
    agent_home: str = "",
) -> str:
    """
    Build the full system message.

    Assembled in order:
        1. Persona prompt
        2. Tool documentation
        3. Installed skills index
        4. Lessons learned
        5. Long-term memory index
        6. System snapshot
    """
    persona = load_persona(project_dir, persona_name)
    rules = load_rules(project_dir)

    tool_docs = TOOL_DOCS_BASE.format(tool_count=4)
    tool_docs += "\n\n" + TOOL_DOCS_RULES

    parts = [persona]
    if rules:
        parts.append("")
        parts.append(rules)
    parts.append("")
    parts.append(tool_docs)

    if skills_dir:
        skills = scan_skills(skills_dir)
        enabled_skills = [s for s in skills if s.get("enabled")]
        if enabled_skills:
            parts.append("")
            parts.append("## Installed Skills")
            parts.append("")
            parts.append(
                f"Your skills are in `{skills_dir}`. "
                "**Before starting any building or coding work, read the "
                "relevant skill first** using `read_file`. Each skill has a "
                "`SKILL.md` with guidelines you must follow."
            )
            parts.append("")
            parts.append("| Skill | Description |")
            parts.append("|-------|-------------|")
            for s in enabled_skills:
                desc = s.get("description", "") or s.get("title", s["name"])
                parts.append(f"| {s['name']} | {desc} |")

    if agent_home:
        lessons = load_lessons(agent_home)
        if lessons:
            parts.append("")
            parts.append("## Lessons Learned")
            parts.append("")
            parts.append(lessons)

    if agent_home:
        memory_index = load_memory_index(agent_home)
        if memory_index:
            parts.append("")
            parts.append("## Long-term Memory")
            parts.append("")
            parts.append(memory_index)
            parts.append("")
            parts.append(
                f"> Your full memory directory is at `{os.path.join(agent_home, 'memory')}`. "
                "Keep INDEX.md as a concise index; store details in separate files there."
            )

    if data_dir:
        snapshot = load_snapshot(data_dir)
        snapshot_md = render_snapshot_markdown(snapshot)
        if snapshot_md:
            parts.append("")
            parts.append(snapshot_md)

    return "\n".join(parts)


def get_today_feed(data_dir: str) -> list[dict]:
    feed_path = os.path.join(data_dir, "feed.jsonl")
    if not os.path.exists(feed_path):
        return []

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    entries = []
    try:
        with open(feed_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = obj.get("timestamp", "")
                if ts.startswith(today):
                    entries.append({
                        "round": obj.get("round", "?"),
                        "time": ts[11:16],
                        "content": obj.get("content", ""),
                    })
    except OSError:
        pass
    return entries


def build_context_messages(
    round_num: int,
    max_tool_calls: int,
    memory: MemoryManager,
    agent_home: str,
    data_dir: str = "",
    history_rounds: int = 3,
) -> list[dict]:
    """Build the multi-turn context messages for a new round."""
    messages = []

    recent_timeline = memory.get_recent_timeline(count=history_rounds)
    if recent_timeline:
        for entry in recent_timeline:
            r = entry.get("round", "?")
            ts = entry.get("timestamp", "")
            tools = entry.get("tools_used", 0)
            dur = entry.get("duration", 0)
            summary = entry.get("summary", "")

            final_output = _extract_final_output(summary)
            if not final_output:
                final_output = "(no output)"

            messages.append({
                "role": "user",
                "content": f"Round {r} | {ts} | Tools: {tools} | {dur}s",
            })
            messages.append({
                "role": "assistant",
                "content": final_output,
            })

    inspiration = memory.read_inspiration()
    if inspiration:
        messages.append({
            "role": "system",
            "content": (
                "A sudden spark of inspiration crosses your mind: "
                f'"{inspiration}"'
            ),
        })

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    wakeup_parts = [
        f"Current time: {now}",
        f"Round {round_num} (tool budget: {max_tool_calls})",
    ]

    if data_dir:
        today_feed = get_today_feed(data_dir)
        if today_feed:
            wakeup_parts.append("")
            wakeup_parts.append(f"Today's activity ({len(today_feed)} rounds so far):")
            for item in today_feed:
                wakeup_parts.append(f"- [{item['time']}] Round {item['round']}: {item['content']}")

    wakeup_parts.append("")
    wakeup_parts.append(f"You wake up. Your home directory is `{agent_home}`.")

    messages.append({
        "role": "user",
        "content": "\n".join(wakeup_parts),
    })

    return messages
