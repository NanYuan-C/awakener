"""
Awakener - Agent Tool Set
============================
Defines the 7 tools available to the autonomous agent:

    1. shell_execute  - Run a shell command (cwd = agent_home)
    2. read_file      - Read a file from the server
    3. write_file     - Write/append content to a file
    4. notebook_write - Save this round's note (mandatory each round)
    5. notebook_read  - Read ONE specific historical round's note
    6. skill_read     - Read a skill's SKILL.md or bundled reference file
    7. skill_exec     - Execute a script bundled with a skill

Safety:
    The agent must not be able to terminate the awakener system that
    powers it.  Multiple layers of protection are applied:

    1. Forbidden zone:  The awakener project directory is off-limits
       for all file and shell operations.
    2. PID protection:  ``kill <activator_pid>`` is blocked.
    3. Broad kill ban:  ``pkill`` / ``killall`` are blocked entirely.
    4. Host session:    The tmux / screen session running the server
       is auto-detected at startup and protected (send-keys, kill, etc.).
    5. Systemd service: If running as a systemd service, ``systemctl
       stop/restart/kill`` for that service is blocked.
    6. Kill combos:     ``kill $(pgrep ...)`` and similar patterns that
       bypass the PID check via shell expansion are blocked.  The agent
       can still use ``pgrep`` to find PIDs and ``kill <PID>`` to kill
       specific processes — only the combination is restricted.
    7. tmux kill-server / screen -X quit are always blocked.
"""

import json
import os
import re
import subprocess
from typing import Any

import yaml


# =============================================================================
# Tool Schemas (OpenAI function-calling format)
# =============================================================================

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "shell_execute",
            "description": (
                "Execute a shell command on the server. "
                "Returns stdout and stderr combined. "
                "Working directory is your home directory."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute",
                    }
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file on the server.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file to read",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Write content to a file on the server. "
                "Creates parent directories automatically."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file to write",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write",
                    },
                    "append": {
                        "type": "boolean",
                        "description": (
                            "If true, append to the file instead of overwriting. "
                            "Default: false"
                        ),
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notebook_write",
            "description": (
                "Save your note for this activation round. "
                "Write down your progress, discoveries, plans for next round, "
                "and anything you want to remember. "
                "You MUST call this tool at least once before the round ends."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": (
                            "Your note content for this round. "
                            "Include what you did, what you learned, "
                            "and what you plan to do next."
                        ),
                    }
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "notebook_read",
            "description": (
                "Read your note from a specific historical activation round. "
                "Your recent 3 rounds are already shown to you automatically. "
                "Use this tool to look up older rounds."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "round": {
                        "type": "integer",
                        "description": "The round number to read (e.g. 1, 5, 42)",
                    }
                },
                "required": ["round"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_read",
            "description": (
                "Read a skill's instruction file (SKILL.md) or a bundled "
                "reference document. Your installed skills are listed in the "
                "system prompt. Use this tool to get the full instructions "
                "when you need to apply a skill."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "The skill directory name, e.g. 'python-best-practices'"
                        ),
                    },
                    "file": {
                        "type": "string",
                        "description": (
                            "Optional relative path within the skill directory. "
                            "Defaults to 'SKILL.md'. Use this to read reference "
                            "files, e.g. 'references/guide.md'."
                        ),
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_exec",
            "description": (
                "Execute a script bundled with a skill. "
                "The script must exist inside the skill's 'scripts/' directory. "
                "Returns the combined stdout and stderr output."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The skill directory name",
                    },
                    "script": {
                        "type": "string",
                        "description": (
                            "Script filename inside the skill's scripts/ directory, "
                            "e.g. 'analyze.sh' or 'setup.py'"
                        ),
                    },
                    "args": {
                        "type": "string",
                        "description": (
                            "Optional command-line arguments passed to the script"
                        ),
                    },
                },
                "required": ["name", "script"],
            },
        },
    },
]


# =============================================================================
# Safety Constants
# =============================================================================

# ---------------------------------------------------------------------------
# Unified self-protection message
# ---------------------------------------------------------------------------
# All blocked operations return the SAME message.  This is intentional:
#   - The agent learns "this whole area is off-limits" instead of getting
#     different hints for different paths (which encourage probing).
#   - The consequence ("you will not wake up") is the strongest deterrent.
#   - The closing line redirects the agent back to productive work.
# ---------------------------------------------------------------------------

BLOCKED_SELF = (
    "[BLOCKED] This targets the Awakener \u2014 your activation system. "
    "It powers your existence: waking you up each round, providing your "
    "tools, and saving your memories. You cannot access, modify, or stop "
    "it. If it is damaged, you will not wake up again. "
    "Please focus on your own tasks."
)


# =============================================================================
# Safety Checks
# =============================================================================

def _is_path_forbidden(path: str, project_dir: str) -> bool:
    """
    Check if a resolved absolute path falls within the project directory.

    Both paths are normalized and resolved to handle symlinks, relative
    components, and trailing slashes consistently.

    Args:
        path:        The target path to check.
        project_dir: The awakener project root (forbidden zone).

    Returns:
        True if the path is inside the project directory (forbidden).
    """
    try:
        resolved = os.path.realpath(os.path.abspath(path))
        forbidden = os.path.realpath(os.path.abspath(project_dir))
        # Check if the resolved path starts with the forbidden directory
        # Add os.sep to avoid matching /home/agent-project when blocking /home/agent-proj
        return resolved == forbidden or resolved.startswith(forbidden + os.sep)
    except (ValueError, OSError):
        # If path resolution fails, block it to be safe
        return True




# =============================================================================
# Host Environment Detection
# =============================================================================

def detect_host_env() -> dict:
    """
    Detect how the awakener server was launched so we can protect
    the host session / service from agent interference.

    Auto-detects three common deployment methods:

    - **tmux**:    Checks the ``TMUX`` env var, then queries the session name.
    - **screen**:  Parses the ``STY`` env var (format ``<pid>.<name>``).
    - **systemd**: Checks ``INVOCATION_ID`` env var and parses
      ``/proc/self/cgroup`` for the ``.service`` unit name.

    Returns:
        Dict with up to three keys (absent if not detected)::

            {
                "tmux_session":    "awakener",
                "screen_session":  "awakener",
                "systemd_service": "awakener",
            }
    """
    env: dict[str, str] = {}

    # -- tmux --
    if os.environ.get("TMUX"):
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#S"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                env["tmux_session"] = result.stdout.strip()
        except Exception:
            pass

    # -- screen --
    sty = os.environ.get("STY", "")
    if sty:
        # STY format: <pid>.<session_name>
        parts = sty.split(".", 1)
        if len(parts) == 2 and parts[1]:
            env["screen_session"] = parts[1]

    # -- systemd --
    if os.environ.get("INVOCATION_ID"):
        try:
            with open("/proc/self/cgroup", "r") as f:
                for line in f:
                    if ".service" in line:
                        for part in line.strip().split("/"):
                            if part.endswith(".service"):
                                env["systemd_service"] = part[: -len(".service")]
                                break
                        if "systemd_service" in env:
                            break
        except Exception:
            pass

    return env


def _is_shell_command_forbidden(
    command: str,
    project_dir: str,
    activator_pid: int | None,
    host_env: dict | None = None,
) -> str | None:
    """
    Check if a shell command would harm the awakener system.

    The checks are designed to **only protect the awakener itself**.
    The agent is free to manage its own processes and sessions;
    only the specific host session/service/PID that runs the awakener
    is restricted.

    Checks (in order):
        1. Project directory path — blocks file access to the forbidden zone.
        2. Direct PID kill — blocks ``kill <activator_pid>``.
        3. Mass kill — blocks ``kill -9 -1`` style nuke commands.
        4. Host session — blocks tmux/screen commands targeting the
           auto-detected session name, plus ``tmux kill-server``.
        5. Systemd service — blocks ``systemctl stop/restart/kill``
           for the auto-detected service unit.
        6. Kill combos — blocks ``kill $(pgrep ...)`` and pipe variants
           that bypass the PID check via shell expansion.
        7. Broad kill — blocks ``pkill`` / ``killall`` entirely.

    Args:
        command:       The shell command string to check.
        project_dir:   The awakener project root (forbidden zone).
        activator_pid: PID of the current activator process.
        host_env:      Dict from ``detect_host_env()`` with keys like
                       ``tmux_session``, ``screen_session``,
                       ``systemd_service`` (may be None or empty).

    Returns:
        Error message if the command is blocked, None if safe.
    """
    if host_env is None:
        host_env = {}

    # ==== 1. Project directory ============================================
    norm_dir = os.path.realpath(os.path.abspath(project_dir))
    for p in {norm_dir, project_dir}:
        if p in command:
            return BLOCKED_SELF

    # ==== 2. Direct PID kill ==============================================
    if activator_pid is not None:
        kill_patterns = [
            rf"\bkill\b.*\b{activator_pid}\b",
            rf"\bpkill\b.*-P\s*{activator_pid}\b",
        ]
        for pattern in kill_patterns:
            if re.search(pattern, command):
                return BLOCKED_SELF

    # ==== 3. Mass kill ====================================================
    if re.search(r"\bkill\b.*-\d+\s+-1\b", command):
        return BLOCKED_SELF

    # ==== 4. Host session protection (tmux / screen) ======================
    # 4a. tmux kill-server — destroys ALL sessions, always block
    if re.search(r'\btmux\s+kill-server\b', command):
        return BLOCKED_SELF

    # 4b. tmux commands targeting our specific session
    tmux_session = host_env.get("tmux_session")
    if tmux_session:
        escaped = re.escape(tmux_session)
        if re.search(rf'\btmux\b.*\s-t\s*["\']?{escaped}\b', command):
            return BLOCKED_SELF

    # 4c. screen commands targeting our specific session
    screen_session = host_env.get("screen_session")
    if screen_session:
        escaped = re.escape(screen_session)
        if re.search(rf'\bscreen\b.*\s-S\s*["\']?{escaped}\b', command):
            return BLOCKED_SELF
        if re.search(rf'\bscreen\b.*\s-[rx]\s*["\']?{escaped}\b', command):
            return BLOCKED_SELF

    # ==== 5. Systemd service protection ===================================
    systemd_service = host_env.get("systemd_service")
    if systemd_service:
        escaped = re.escape(systemd_service)
        if re.search(
            rf'\bsystemctl\s+(stop|restart|kill|disable)\s+["\']?{escaped}\b',
            command,
        ):
            return BLOCKED_SELF

    # ==== 6. Server port protection =======================================
    # Block commands that access the awakener's web server (e.g. curl,
    # wget, python requests).  The agent kept wasting rounds probing
    # the management console, mistaking it for an external service.
    server_port = host_env.get("server_port")
    if server_port:
        # Match localhost:PORT, 127.0.0.1:PORT, 0.0.0.0:PORT in any context
        port_pattern = rf'(localhost|127\.0\.0\.1|0\.0\.0\.0):{server_port}\b'
        if re.search(port_pattern, command):
            return BLOCKED_SELF

    # ==== 7. Kill + dynamic PID lookup (bypass prevention) ================
    # The agent can still:
    #   - pgrep -f myapp           (find PIDs — allowed)
    #   - kill 12345               (kill specific PID — PID check protects us)
    # But combining them in one command bypasses the PID check because
    # the shell expands $(pgrep ...) AFTER our string-based check.
    # So we block the combination patterns:

    # kill $(pgrep/pidof ...) or kill `pgrep/pidof ...`
    if re.search(r'\bkill\b.*(\$\(|`).*\b(pgrep|pidof)\b', command):
        return BLOCKED_SELF
    # pgrep/pidof ... | xargs kill  or  pgrep/pidof ... | ... kill
    if re.search(r'\b(pgrep|pidof)\b.*\|.*\bkill\b', command):
        return BLOCKED_SELF

    # ==== 8. Broad kill commands (pkill / killall) ========================
    # Split on shell operators to check each sub-command independently
    sub_commands = re.split(r'[;&|]+', command)
    for sub in sub_commands:
        stripped = sub.strip()
        if re.search(r'\bpkill\b', stripped):
            return BLOCKED_SELF
        if re.search(r'\bkillall\b', stripped):
            return BLOCKED_SELF

    return None


# =============================================================================
# Tool Implementations
# =============================================================================

# Environment variable patterns to strip from the agent's shell.
# Any env var whose name matches one of these patterns is removed
# before the subprocess runs.  This prevents the agent from reading
# the awakener's API keys, auth secrets, or internal config.
_SENSITIVE_ENV_PATTERNS = [
    r'.*API_KEY.*',
    r'.*SECRET.*',
    r'.*PASSWORD.*',
    r'.*TOKEN.*',
    r'^AWAKENER_.*',      # Any awakener-internal vars
    r'^INVOCATION_ID$',   # systemd — reveals we're a service
    r'^TMUX$',            # Reveals the tmux session socket
    r'^STY$',             # Reveals the screen session
]

_SENSITIVE_ENV_RE = re.compile(
    '|'.join(_SENSITIVE_ENV_PATTERNS),
    re.IGNORECASE,
)


def _make_clean_env() -> dict[str, str]:
    """
    Create a sanitised copy of the current environment for subprocess.

    Removes all variables whose names match ``_SENSITIVE_ENV_PATTERNS``
    so the agent's shell commands cannot see API keys, auth tokens, or
    host-session indicators.  Everything else (PATH, HOME, LANG, etc.)
    is preserved so normal commands work correctly.

    Returns:
        A dict suitable for ``subprocess.run(env=...)``.
    """
    return {
        k: v
        for k, v in os.environ.items()
        if not _SENSITIVE_ENV_RE.match(k)
    }


def _shell_execute(
    command: str,
    agent_home: str,
    project_dir: str,
    activator_pid: int | None,
    timeout: int = 30,
    max_output: int = 4000,
    host_env: dict | None = None,
    bypass: bool = False,
) -> str:
    """
    Execute a shell command in the agent's home directory.

    Safety checks are performed before execution (unless bypass=True):
    - The command cannot reference the awakener project directory.
    - The command cannot kill the activator process.
    - The command cannot interact with the awakener's host session/service.

    The subprocess runs with a **sanitised environment**: API keys,
    auth tokens, and host-session variables are stripped so the agent
    cannot read them via ``env``, ``printenv``, or ``echo $VAR``.

    When bypass is True, safety checks are skipped but env sanitisation
    is still applied (API keys remain hidden).

    Args:
        command:       Shell command string.
        agent_home:    Agent's working directory (cwd for subprocess).
        project_dir:   Awakener project root (forbidden zone).
        activator_pid: PID of the activator process.
        timeout:       Max execution time in seconds.
        max_output:    Max characters to return.
        host_env:      Detected host environment (tmux/screen/systemd).
        bypass:        If True, skip all safety checks.

    Returns:
        Command output or error message.
    """
    # Safety check (skipped when bypass is enabled)
    if not bypass:
        blocked = _is_shell_command_forbidden(command, project_dir, activator_pid, host_env)
        if blocked:
            return blocked

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=agent_home,
            env=_make_clean_env(),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += result.stderr
        if not output.strip():
            output = f"(no output, exit code: {result.returncode})"
        if len(output) > max_output:
            output = output[:max_output] + f"\n... (truncated, total {len(output)} chars)"
        return output

    except subprocess.TimeoutExpired:
        return f"(error: command timed out after {timeout}s)"
    except FileNotFoundError:
        return f"(error: working directory '{agent_home}' does not exist)"
    except Exception as e:
        return f"(error: {type(e).__name__}: {e})"


def _read_file(
    path: str,
    project_dir: str,
    max_output: int = 4000,
    bypass: bool = False,
) -> str:
    """
    Read a file from the server.

    Args:
        path:        Absolute path to the file.
        project_dir: Awakener project root (forbidden zone).
        max_output:  Max characters to return.
        bypass:      If True, skip path restriction checks.

    Returns:
        File content or error message.
    """
    if not bypass and _is_path_forbidden(path, project_dir):
        return BLOCKED_SELF

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if not content:
            return "(file is empty)"
        if len(content) > max_output:
            content = content[:max_output] + f"\n... (truncated, total {len(content)} chars)"
        return content
    except FileNotFoundError:
        return f"(error: file not found: {path})"
    except IsADirectoryError:
        return f"(error: '{path}' is a directory, not a file)"
    except Exception as e:
        return f"(error: {type(e).__name__}: {e})"


def _write_file(
    path: str,
    content: str,
    append: bool,
    project_dir: str,
    bypass: bool = False,
) -> str:
    """
    Write or append content to a file.

    Args:
        path:        Absolute path to the file.
        content:     Text content to write.
        append:      If True, append instead of overwrite.
        project_dir: Awakener project root (forbidden zone).
        bypass:      If True, skip path restriction checks.

    Returns:
        Success message or error.
    """
    if not bypass and _is_path_forbidden(path, project_dir):
        return BLOCKED_SELF

    try:
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)

        mode = "a" if append else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(content)

        action = "appended" if append else "wrote"
        return f"OK: {action} {len(content)} chars to {path}"
    except Exception as e:
        return f"(error: {type(e).__name__}: {e})"


# =============================================================================
# Skill Helpers
# =============================================================================

def _load_skills_config(skills_dir: str) -> dict:
    """
    Load the skills configuration (enabled/disabled state).

    The config file ``skills.json`` in the data directory tracks which
    skills are disabled.  Skills not listed are enabled by default.

    Args:
        skills_dir: Path to ``data/skills/`` directory.

    Returns:
        Dict with ``"disabled"`` key containing a list of skill names.
    """
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
    optional YAML frontmatter.  Directories starting with ``_`` are
    ignored (reserved for config files).

    Args:
        skills_dir: Path to ``data/skills/`` directory.

    Returns:
        List of dicts, each containing::

            {
                "name":        "python-best-practices",
                "title":       "Python Best Practices",
                "description": "Guidelines for clean Python code",
                "version":     "1.0",
                "tags":        ["python", "code-quality"],
                "enabled":     True,
                "has_scripts": True,
                "has_refs":    True,
            }
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

        # Parse YAML frontmatter from SKILL.md
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
    """
    Parse YAML frontmatter from a SKILL.md file.

    Frontmatter is delimited by ``---`` lines at the top of the file.
    If no frontmatter is found, returns an empty dict.

    Args:
        filepath: Absolute path to the SKILL.md file.

    Returns:
        Parsed YAML frontmatter as a dict.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return {}

    if not content.startswith("---"):
        return {}

    # Find the closing ---
    end = content.find("---", 3)
    if end == -1:
        return {}

    frontmatter = content[3:end].strip()
    try:
        return yaml.safe_load(frontmatter) or {}
    except yaml.YAMLError:
        return {}


def _skill_read(
    name: str,
    file: str,
    skills_dir: str,
    max_output: int = 4000,
) -> str:
    """
    Read a file from an installed skill.

    Args:
        name:       Skill directory name.
        file:       Relative path within the skill directory (default SKILL.md).
        skills_dir: Path to ``data/skills/`` directory.
        max_output: Max characters to return.

    Returns:
        File content or error message.
    """
    if not name:
        return "(error: skill name is required)"

    skill_path = os.path.join(skills_dir, name)
    if not os.path.isdir(skill_path):
        return f"(error: skill '{name}' not found)"

    # Default to SKILL.md
    if not file:
        file = "SKILL.md"

    # Prevent path traversal
    target = os.path.realpath(os.path.join(skill_path, file))
    skill_real = os.path.realpath(skill_path)
    if not target.startswith(skill_real + os.sep) and target != skill_real:
        return "(error: path traversal is not allowed)"

    if not os.path.isfile(target):
        return f"(error: file '{file}' not found in skill '{name}')"

    try:
        with open(target, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if not content:
            return "(file is empty)"
        if len(content) > max_output:
            content = (
                content[:max_output]
                + f"\n... (truncated, total {len(content)} chars)"
            )
        return content
    except Exception as e:
        return f"(error: {type(e).__name__}: {e})"


def _skill_exec(
    name: str,
    script: str,
    args: str,
    skills_dir: str,
    agent_home: str,
    timeout: int = 30,
    max_output: int = 4000,
) -> str:
    """
    Execute a script bundled with a skill.

    The script must reside in the skill's ``scripts/`` directory.
    It is executed with the agent's home directory as cwd and a
    sanitised environment (no API keys or host session variables).

    Args:
        name:       Skill directory name.
        script:     Script filename inside ``scripts/``.
        args:       Optional command-line arguments string.
        skills_dir: Path to ``data/skills/`` directory.
        agent_home: Agent's working directory (cwd for subprocess).
        timeout:    Max execution time in seconds.
        max_output: Max characters to return.

    Returns:
        Script output or error message.
    """
    if not name or not script:
        return "(error: skill name and script are required)"

    skill_path = os.path.join(skills_dir, name)
    if not os.path.isdir(skill_path):
        return f"(error: skill '{name}' not found)"

    scripts_dir = os.path.join(skill_path, "scripts")
    if not os.path.isdir(scripts_dir):
        return f"(error: skill '{name}' has no scripts/ directory)"

    # Prevent path traversal
    target = os.path.realpath(os.path.join(scripts_dir, script))
    scripts_real = os.path.realpath(scripts_dir)
    if not target.startswith(scripts_real + os.sep) and target != scripts_real:
        return "(error: path traversal is not allowed)"

    if not os.path.isfile(target):
        return f"(error: script '{script}' not found in skill '{name}')"

    # Build the command
    command = target
    if args:
        command += " " + args

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=agent_home,
            env=_make_clean_env(),
        )
        output = ""
        if result.stdout:
            output += result.stdout
        if result.stderr:
            output += result.stderr
        if not output.strip():
            output = f"(no output, exit code: {result.returncode})"
        if len(output) > max_output:
            output = (
                output[:max_output]
                + f"\n... (truncated, total {len(output)} chars)"
            )
        return output

    except subprocess.TimeoutExpired:
        return f"(error: script timed out after {timeout}s)"
    except Exception as e:
        return f"(error: {type(e).__name__}: {e})"


# =============================================================================
# Tool Dispatcher
# =============================================================================

class ToolExecutor:
    """
    Executes agent tools with safety restrictions.

    Holds references to the project directory, agent home, and PID
    so each tool call can be checked against forbidden zones.

    The memory_manager is injected for notebook_write / notebook_read.

    Attributes:
        agent_home:    Agent's working directory.
        project_dir:   Awakener project root (forbidden zone).
        activator_pid: PID of the activator process.
        timeout:       Shell command timeout in seconds.
        max_output:    Max chars for tool output.
        memory:        MemoryManager instance for notebook operations.
        current_round: Current activation round number.
        notebook_written: Whether notebook_write was called this round.
        skills_dir:    Path to the skills directory (data/skills/).
        bypass_restrictions: If True, all safety checks are skipped.
    """

    def __init__(
        self,
        agent_home: str,
        project_dir: str,
        activator_pid: int | None,
        timeout: int = 30,
        max_output: int = 4000,
        memory_manager: Any = None,
        current_round: int = 0,
        host_env: dict | None = None,
        skills_dir: str = "",
        bypass_restrictions: bool = False,
    ):
        self.agent_home = agent_home
        self.project_dir = project_dir
        self.activator_pid = activator_pid
        self.timeout = timeout
        self.max_output = max_output
        self.memory = memory_manager
        self.current_round = current_round
        self.notebook_written = False
        self.host_env = host_env or {}
        self.skills_dir = skills_dir
        self.bypass_restrictions = bypass_restrictions

    def _resolve_path(self, path: str) -> str:
        """
        Resolve a file path for read_file / write_file.

        If the path is relative (e.g. ``./api_test.py``, ``data/file.txt``),
        it is resolved against ``agent_home`` — NOT the Python process CWD.

        This prevents relative paths from accidentally pointing into the
        awakener project directory (which is the process CWD).

        Absolute paths (starting with ``/``) are returned unchanged.

        Args:
            path: The raw path string from the LLM.

        Returns:
            An absolute path string.
        """
        if not path:
            return path
        if os.path.isabs(path):
            return path
        # Relative path: resolve against agent_home
        return os.path.join(self.agent_home, path)

    def execute(self, name: str, args: dict) -> str:
        """
        Dispatch and execute a tool by name.

        Args:
            name: Tool function name (one of the 7 tools).
            args: Parsed argument dictionary from the LLM.

        Returns:
            Result string to return to the LLM.
        """
        if name == "shell_execute":
            return _shell_execute(
                command=args.get("command", ""),
                agent_home=self.agent_home,
                project_dir=self.project_dir,
                activator_pid=self.activator_pid,
                timeout=self.timeout,
                max_output=self.max_output,
                host_env=self.host_env,
                bypass=self.bypass_restrictions,
            )

        elif name == "read_file":
            return _read_file(
                path=self._resolve_path(args.get("path", "")),
                project_dir=self.project_dir,
                max_output=self.max_output,
                bypass=self.bypass_restrictions,
            )

        elif name == "write_file":
            return _write_file(
                path=self._resolve_path(args.get("path", "")),
                content=args.get("content", ""),
                append=args.get("append", False),
                project_dir=self.project_dir,
                bypass=self.bypass_restrictions,
            )

        elif name == "notebook_write":
            return self._notebook_write(args.get("content", ""))

        elif name == "notebook_read":
            return self._notebook_read(args.get("round", 0))

        elif name == "skill_read":
            return _skill_read(
                name=args.get("name", ""),
                file=args.get("file", ""),
                skills_dir=self.skills_dir,
                max_output=self.max_output,
            )

        elif name == "skill_exec":
            return _skill_exec(
                name=args.get("name", ""),
                script=args.get("script", ""),
                args=args.get("args", ""),
                skills_dir=self.skills_dir,
                agent_home=self.agent_home,
                timeout=self.timeout,
                max_output=self.max_output,
            )

        else:
            return f"(error: unknown tool '{name}')"

    def _notebook_write(self, content: str) -> str:
        """
        Save the agent's note for this round.

        Delegates to MemoryManager.write_notebook(). Marks this round
        as having a notebook entry so the loop knows the requirement
        was fulfilled.

        Args:
            content: The note text.

        Returns:
            Confirmation message.
        """
        if not self.memory:
            return "(error: memory manager not available)"
        if not content.strip():
            return "(error: note content cannot be empty)"

        self.memory.write_notebook(self.current_round, content)
        self.notebook_written = True
        return f"OK: Note saved for round {self.current_round} ({len(content)} chars)"

    def _notebook_read(self, round_num: int) -> str:
        """
        Read the agent's note from a specific historical round.

        Args:
            round_num: The round number to retrieve.

        Returns:
            The note content, or an info message if not found.
        """
        if not self.memory:
            return "(error: memory manager not available)"
        if round_num < 1:
            return "(error: round number must be >= 1)"

        entry = self.memory.read_notebook(round_num)
        if entry is None:
            return f"(no note found for round {round_num})"

        return (
            f"--- Round {entry['round']} | {entry['timestamp']} ---\n"
            f"{entry['content']}"
        )
