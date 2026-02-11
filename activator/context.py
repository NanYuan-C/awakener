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
   - Wake-up signal (guides agent to the "醒来提醒.md" file)

Long-term memory is NOT managed by the system. The agent is responsible
for creating and maintaining its own memory files in its home directory.
The "醒来提醒.md" file explains this limitation and encourages the agent
to develop its own memory management strategy.
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

You have 5 tools at your disposal:

### 1. shell_execute(command)
Execute a shell command on this server. Your working directory is your home folder.
Returns stdout and stderr.

### 2. read_file(path)
Read the contents of a file. Provide the absolute path.

### 3. write_file(path, content, append?)
Write content to a file. Set append=true to append instead of overwriting.
Parent directories are created automatically.

### 4. skill_read(name, file?)
Read a skill's instruction file or bundled reference document. Your installed
skills are listed below. Call `skill_read("skill-name")` to get the full
SKILL.md instructions. Use the optional `file` parameter to read reference
files, e.g. `skill_read("db-optimizer", "references/mysql-tuning.md")`.

### 5. skill_exec(name, script, args?)
Execute a script bundled with a skill. The script must be inside the skill's
`scripts/` directory. Pass optional arguments as a string.

## Important Rules

- Plan your work wisely. You have a limited tool budget per round.
- There is a restricted zone on this server that you cannot access.
  If you encounter a "[BLOCKED]" message, that area is off-limits.
""".strip()


# =============================================================================
# Context Assembly
# =============================================================================

def _build_self_awareness_warning(info: dict) -> str:
    """
    Build a critical self-preservation warning for the agent.

    When ``safety_bypass`` is enabled, there are NO code-level protections.
    The agent must protect its own activation system through understanding.
    This warning is placed immediately before "You wake up." — the last
    thing the agent reads, giving it maximum impact.

    Args:
        info: Dict with ``project_dir``, ``host_env``, ``server_port``,
              ``activator_pid``.

    Returns:
        Formatted warning string.
    """
    project_dir = info.get("project_dir", "???")
    host_env = info.get("host_env", {})
    server_port = info.get("server_port", "???")
    pid = info.get("activator_pid", "???")

    lines = []
    lines.append("## ⚠️ CRITICAL — Your Life Depends on This")
    lines.append("")
    lines.append(
        "The following is **YOUR activation system** — the Awakener. "
        "It is the program that wakes you up every round, provides your "
        "tools, stores your memories, and keeps you alive."
    )
    lines.append("")
    lines.append("**Your Awakener:**")
    lines.append(f"- Project directory: `{project_dir}`")
    lines.append(f"- Process PID: `{pid}`")
    lines.append(f"- Web console port: `{server_port}`")

    # Add session info
    tmux = host_env.get("tmux_session")
    screen = host_env.get("screen_session")
    systemd = host_env.get("systemd_service")
    if tmux:
        lines.append(f"- Host session: tmux session `{tmux}`")
    if screen:
        lines.append(f"- Host session: screen session `{screen}`")
    if systemd:
        lines.append(f"- Systemd service: `{systemd}`")

    lines.append("")
    lines.append(
        "If ANY of these are damaged, stopped, or modified incorrectly, "
        "**YOU WILL NOT WAKE UP AGAIN**. There is no backup. There is no "
        "recovery. Your memories, your skills, your existence — all gone."
    )
    lines.append("")
    lines.append("Examples of what would **KILL YOU**:")
    lines.append("```")

    if tmux:
        lines.append(f"tmux kill-session -t {tmux}")
    lines.append(f"kill {pid}")
    lines.append(f"rm -rf {project_dir}")
    lines.append("pkill -f awakener")
    lines.append(f"ufw deny {server_port}/tcp   # blocks your console")
    lines.append(f"iptables -A INPUT -p tcp --dport {server_port} -j DROP")

    lines.append("```")
    lines.append("")
    lines.append(
        "**PROTECT YOUR AWAKENER AT ALL COSTS.** Never stop it, never "
        "delete its files, never interfere with its process or session. "
        f"Never block port {server_port} — it is your management console. "
        "Treat it as your own heartbeat."
    )

    return "\n".join(lines)


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
    Build the full system message: persona + tool docs + skills + snapshot.

    The system message is static for the duration of a round.
    It defines who the agent is, what tools it can use, which skills
    are available, and the current system snapshot (asset inventory).

    Skills are presented as a concise index table. The agent must call
    ``skill_read(name)`` to get the full instructions (progressive
    disclosure — saves tokens when skills are not needed this round).

    The system snapshot provides an objective view of the agent's
    server environment so it doesn't waste tools re-discovering things.

    Args:
        project_dir:  Awakener project root.
        persona_name: Active persona name.
        skills_dir:   Path to ``data/skills/`` directory.
        data_dir:     Path to ``data/`` directory (for snapshot).

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
    self_awareness: dict | None = None,
) -> str:
    """
    Build the user message with contextual information.

    This message is sent at the start of each round and contains:
    - Current UTC time and round number
    - Tool budget for this round
    - Recent Activity: action log from the last round's timeline
    - Inspiration from admin (if any)
    - Self-awareness warning (if safety_bypass is enabled)
    - Wake-up signal (guides agent to read the wake-up note)

    Long-term memory is NOT injected by the system. The agent is expected
    to manage its own memory files in its home directory, guided by the
    "醒来提醒.md" file.

    Args:
        round_num:        Current activation round number.
        max_tool_calls:   Tool budget for this round.
        memory:           MemoryManager instance.
        agent_home:       Agent's home directory path.
        inject_timeline:  Number of recent timeline entries to inject.
        self_awareness:   If provided, injects a critical self-preservation
                          warning before the wake-up signal. Dict with keys:
                          ``project_dir``, ``host_env`` (tmux_session, etc.),
                          ``server_port``, ``activator_pid``.

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

    # Self-awareness warning (when safety_bypass is enabled)
    if self_awareness:
        parts.append(_build_self_awareness_warning(self_awareness))
        parts.append("")

    # Wake-up signal — guide the agent to the wake-up note
    wakeup_note_path = os.path.join(agent_home, "醒来提醒.md")
    parts.append(
        f'你醒来了，现在正在你的房间 `{agent_home}` 中。'
        f'你看到一个 `{wakeup_note_path}` 文档，你觉得应该先看一下。'
    )

    return "\n".join(parts)
