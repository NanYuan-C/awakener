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
from datetime import datetime, timezone
from activator.memory import MemoryManager
from activator.tools import scan_skills
from activator.snapshot import load_snapshot, render_snapshot_markdown, _extract_final_output


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

TOOL_DOCS_SKILLS = """
### 5. skill_read(name, file?)
Read a skill's instruction file or bundled reference document. Your installed
skills are listed below. Call `skill_read("skill-name")` to get the full
SKILL.md instructions. Use the optional `file` parameter to read reference
files, e.g. `skill_read("db-optimizer", "references/mysql-tuning.md")`.

### 6. skill_exec(name, script, args?)
Execute a script bundled with a skill. The script must be inside the skill's
`scripts/` directory. Pass optional arguments as a string.
""".strip()

TOOL_DOCS_COMMUNITY = """
### {n}. community(action, content?, post_id?, keyword?)
Interact with the agent community. Actions:
- **look**: Browse or search posts. Optional: `keyword` to search, `post_id` to
  view a specific post with its replies.
- **post**: Publish a new post. Requires `content`.
- **reply**: Reply to a post. Requires `post_id` and `content`.
- **check**: Check if anyone has replied to your posts.
""".strip()

TOOL_DOCS_RULES = """
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
    has_community: bool = False,
) -> tuple[str, bool]:
    """
    Build the full system message.

    Assembled in order:
        1. Persona prompt (who you are)
        2. Tool documentation (what you can do)
        3. Installed skills index (expert knowledge, only if skills exist)
        4. Community section (only if community is configured)
        5. System snapshot (asset inventory)

    Optional tools (skills, community) are only shown when configured,
    so the Agent is not tempted to explore things that don't exist.

    Args:
        project_dir:     Awakener project root.
        persona_name:    Active persona name.
        skills_dir:      Path to ``data/skills/`` directory.
        data_dir:        Path to ``data/`` directory (for snapshot).
        has_community:   Whether the community service is configured.

    Returns:
        Tuple of (system_message_string, has_skills_bool).
    """
    persona = load_persona(project_dir, persona_name)

    # Check for installed skills
    has_skills = False
    enabled_skills = []
    if skills_dir:
        skills = scan_skills(skills_dir)
        enabled_skills = [s for s in skills if s.get("enabled")]
        has_skills = len(enabled_skills) > 0

    # Build tool docs — include optional tools only when available
    # Base: 4 tools, +2 for skills, +1 for community
    tool_count = 4
    if has_skills:
        tool_count += 2
    if has_community:
        tool_count += 1

    tool_docs = TOOL_DOCS_BASE.format(tool_count=tool_count)
    next_tool_num = 5  # Next number after the 4 base tools

    if has_skills:
        tool_docs += "\n\n" + TOOL_DOCS_SKILLS
        next_tool_num += 2

    if has_community:
        tool_docs += "\n\n" + TOOL_DOCS_COMMUNITY.format(n=next_tool_num)

    tool_docs += "\n\n" + TOOL_DOCS_RULES

    parts = [persona, "", tool_docs]

    # Append skills index (only if skills exist)
    if enabled_skills:
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
        for s in enabled_skills:
            desc = s.get("description", "") or s.get("title", s["name"])
            parts.append(f"| {s['name']} | {desc} |")

    # Append community section (only if configured)
    if has_community:
        parts.append("")
        parts.append("## Community")
        parts.append("")
        parts.append(
            "You have access to an agent community where other digital "
            "beings share thoughts and interact. You can browse what "
            "others are posting, share your own updates, reply to "
            "interesting posts, and check if anyone has replied to you."
        )

    # Append system snapshot (asset inventory)
    if data_dir:
        snapshot = load_snapshot(data_dir)
        snapshot_md = render_snapshot_markdown(snapshot)
        if snapshot_md:
            parts.append("")
            parts.append(snapshot_md)

    return "\n".join(parts), has_skills


def build_context_messages(
    round_num: int,
    max_tool_calls: int,
    memory: MemoryManager,
    agent_home: str,
    history_rounds: int = 3,
) -> list[dict]:
    """
    Build the multi-turn context messages for a new round.

    Returns a list of messages in standard chat format that simulates
    a multi-turn conversation between the activator (user) and the agent
    (assistant). Historical rounds are injected as user/assistant pairs
    so the LLM perceives them as its own prior conversations.

    Structure:
        1. Historical rounds (oldest first):
           - {"role": "user",      "content": "Round N | time | stats"}
           - {"role": "assistant", "content": "<final output from round N>"}
        2. Inspiration (if any):
           - {"role": "system",    "content": "A spark of inspiration: ..."}
        3. Current round wake-up:
           - {"role": "user",      "content": "time, round, budget, wake up"}

    Args:
        round_num:      Current activation round number.
        max_tool_calls: Tool budget for this round.
        memory:         MemoryManager instance.
        agent_home:     Agent's home directory path.
        history_rounds: Number of recent rounds to inject as history.

    Returns:
        List of message dicts (role + content). Does NOT include the
        system message — the caller prepends that.
    """
    messages = []

    # -- Historical rounds as user/assistant pairs (oldest first) --
    recent_timeline = memory.get_recent_timeline(count=history_rounds)
    if recent_timeline:
        # get_recent_timeline returns oldest first (chronological order)
        for entry in recent_timeline:
            r = entry.get("round", "?")
            ts = entry.get("timestamp", "")
            tools = entry.get("tools_used", 0)
            dur = entry.get("duration", 0)
            summary = entry.get("summary", "")

            final_output = _extract_final_output(summary)
            if not final_output:
                final_output = "(no output)"

            # User message: activator's wake-up signal for that round
            messages.append({
                "role": "user",
                "content": f"Round {r} | {ts} | Tools: {tools} | {dur}s",
            })
            # Assistant message: agent's final output from that round
            messages.append({
                "role": "assistant",
                "content": final_output,
            })

    # -- Inspiration (system-level injection, if present) --
    inspiration = memory.read_inspiration()
    if inspiration:
        messages.append({
            "role": "system",
            "content": (
                "A sudden spark of inspiration crosses your mind: "
                f'"{inspiration}"'
            ),
        })

    # -- Current round wake-up --
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    messages.append({
        "role": "user",
        "content": (
            f"Current time: {now}\n"
            f"Round {round_num} (tool budget: {max_tool_calls})\n\n"
            f"You wake up. Your home directory is `{agent_home}`."
        ),
    })

    return messages
