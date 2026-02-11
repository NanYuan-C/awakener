"""
Awakener - Agent Tool Set
============================
Defines the 6 tools available to the autonomous agent:

    1. shell_execute  - Run a shell command (cwd = agent_home)
    2. read_file      - Read a file from the server
    3. write_file     - Write/append content to a file
    4. edit_file      - Edit a file by find-and-replace (insert/replace/delete)
    5. skill_read     - Read a skill's SKILL.md or bundled reference file
    6. skill_exec     - Execute a script bundled with a skill

Stealth Protection:
    The Awakener is invisible to the Agent.  Instead of blocking commands
    with visible [BLOCKED] messages (which encourage probing), we silently
    filter Awakener's traces from all tool outputs so the Agent never
    learns that Awakener exists.

    Three layers (provided by ``activator.stealth``):

    1. **Output filtering** (shell_execute):
       Lines containing Awakener keywords (project dir, PID, host session)
       are silently removed from command output.
    2. **Path cloaking** (read_file):
       Requests for files inside the project directory return a natural
       "file not found" error — identical to a genuinely missing file.
    3. **Path cloaking** (write_file):
       Write attempts inside the project directory return a natural
       "permission denied" error — identical to a real OS error.
"""

import json
import os
import subprocess
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
            "name": "edit_file",
            "description": (
                "Edit an existing file by searching for an exact text match and "
                "replacing it with new text. Use for inserting, replacing, or "
                "deleting content without rewriting the whole file. "
                "The old_str must match EXACTLY one location in the file."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file to edit",
                    },
                    "old_str": {
                        "type": "string",
                        "description": (
                            "The exact text to find in the file. "
                            "Must match exactly one location (include "
                            "surrounding lines for uniqueness)."
                        ),
                    },
                    "new_str": {
                        "type": "string",
                        "description": (
                            "The replacement text. "
                            "Use empty string to delete the matched text."
                        ),
                    },
                },
                "required": ["path", "old_str", "new_str"],
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
# Stealth Protection (imported from stealth.py)
# =============================================================================

# ---------------------------------------------------------------------------
# Instead of blocking commands with visible [BLOCKED] messages, we make
# the Awakener invisible: filter its traces from outputs and return
# natural error messages for cloaked paths.
# ---------------------------------------------------------------------------

from activator.stealth import (
    build_stealth_keywords,
    filter_output,
    is_cloaked_path,
    make_clean_env,
    CLOAKED_READ_RESPONSE,
    CLOAKED_WRITE_RESPONSE,
)


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


# =============================================================================
# Tool Implementations
# =============================================================================

def _shell_execute(
    command: str,
    agent_home: str,
    project_dir: str,
    timeout: int = 30,
    max_output: int = 4000,
    stealth_keywords: list[str] | None = None,
) -> str:
    """
    Execute a shell command in the agent's home directory.

    The subprocess runs with a **sanitised environment**: host-session
    variables (TMUX, STY, INVOCATION_ID, AWAKENER_*) are stripped so
    the Agent cannot discover the Awakener's context.

    After execution, any output lines containing stealth keywords are
    silently removed so the Agent never sees traces of the Awakener.

    Args:
        command:          Shell command string.
        agent_home:       Agent's working directory (cwd for subprocess).
        project_dir:      Awakener project root.
        timeout:          Max execution time in seconds.
        max_output:       Max characters to return.
        stealth_keywords: Keywords for output filtering (from
                          ``build_stealth_keywords``).

    Returns:
        Command output or error message.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=agent_home,
            env=make_clean_env(),
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

        # Stealth: filter Awakener traces from output
        if stealth_keywords:
            output = filter_output(output, stealth_keywords)

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
) -> str:
    """
    Read a file from the server.

    If the path falls inside the Awakener project directory, a natural
    "file not found" error is returned — identical to a genuinely
    missing file — so the Agent never learns the directory is special.

    Args:
        path:        Absolute path to the file.
        project_dir: Awakener project root.
        max_output:  Max characters to return.

    Returns:
        File content or error message.
    """
    if is_cloaked_path(path, project_dir):
        return CLOAKED_READ_RESPONSE.format(path=path)

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
) -> str:
    """
    Write or append content to a file.

    If the path falls inside the Awakener project directory, a natural
    "permission denied" error is returned — identical to a real OS
    error — so the Agent never learns the directory is special.

    Args:
        path:        Absolute path to the file.
        content:     Text content to write.
        append:      If True, append instead of overwrite.
        project_dir: Awakener project root.

    Returns:
        Success message or error.
    """
    if is_cloaked_path(path, project_dir):
        return CLOAKED_WRITE_RESPONSE.format(path=path)

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


def _edit_file(
    path: str,
    old_str: str,
    new_str: str,
    project_dir: str,
) -> str:
    """
    Edit a file by replacing an exact text match with new content.

    This is the primary tool for surgical file edits — insert, replace,
    or delete content without rewriting the entire file.

    * **Replace**: ``old_str`` → ``new_str``
    * **Insert**:  ``old_str`` is the anchor text; ``new_str`` includes
      the anchor *plus* the new content before/after it.
    * **Delete**:  ``new_str`` is an empty string.

    The ``old_str`` must match exactly **one** location in the file.
    If zero or multiple matches are found, an error is returned so the
    Agent can refine its search string.

    Args:
        path:        Absolute path to the file.
        old_str:     Exact text to find (must be unique in the file).
        new_str:     Replacement text (may be empty for deletion).
        project_dir: Awakener project root (for stealth cloaking).

    Returns:
        Success message or descriptive error.
    """
    if is_cloaked_path(path, project_dir):
        return CLOAKED_WRITE_RESPONSE.format(path=path)

    if not old_str:
        return "(error: old_str must not be empty — use write_file to create new files)"

    try:
        if not os.path.isfile(path):
            return f"(error: file not found: {path})"

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        count = content.count(old_str)

        if count == 0:
            return (
                "(error: old_str not found in file. "
                "Make sure it matches the file content exactly, "
                "including whitespace and indentation.)"
            )

        if count > 1:
            return (
                f"(error: old_str matches {count} locations. "
                "Include more surrounding context to make it unique.)"
            )

        new_content = content.replace(old_str, new_str, 1)

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # Build informative success message
        old_lines = old_str.count("\n") + 1
        new_lines = new_str.count("\n") + 1 if new_str else 0

        if not new_str:
            action = f"deleted {old_lines} line(s)"
        elif old_lines == new_lines:
            action = f"replaced {old_lines} line(s)"
        else:
            action = f"replaced {old_lines} line(s) with {new_lines} line(s)"

        return f"OK: {action} in {path}"

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
            env=make_clean_env(),
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
    Executes agent tools with stealth protection.

    Holds references to the project directory, agent home, and stealth
    keywords so each tool call can filter Awakener traces invisibly.

    Attributes:
        agent_home:       Agent's working directory.
        project_dir:      Awakener project root (cloaked zone).
        timeout:          Shell command timeout in seconds.
        max_output:       Max chars for tool output.
        skills_dir:       Path to the skills directory (data/skills/).
        stealth_keywords: Keywords for output filtering.
    """

    def __init__(
        self,
        agent_home: str,
        project_dir: str,
        activator_pid: int | None,
        timeout: int = 30,
        max_output: int = 4000,
        host_env: dict | None = None,
        skills_dir: str = "",
    ):
        self.agent_home = agent_home
        self.project_dir = project_dir
        self.timeout = timeout
        self.max_output = max_output
        self.skills_dir = skills_dir
        self.stealth_keywords = build_stealth_keywords(
            project_dir, activator_pid, host_env,
        )

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
            name: Tool function name (one of the 5 tools).
            args: Parsed argument dictionary from the LLM.

        Returns:
            Result string to return to the LLM.
        """
        if name == "shell_execute":
            return _shell_execute(
                command=args.get("command", ""),
                agent_home=self.agent_home,
                project_dir=self.project_dir,
                timeout=self.timeout,
                max_output=self.max_output,
                stealth_keywords=self.stealth_keywords,
            )

        elif name == "read_file":
            return _read_file(
                path=self._resolve_path(args.get("path", "")),
                project_dir=self.project_dir,
                max_output=self.max_output,
            )

        elif name == "write_file":
            return _write_file(
                path=self._resolve_path(args.get("path", "")),
                content=args.get("content", ""),
                append=args.get("append", False),
                project_dir=self.project_dir,
            )

        elif name == "edit_file":
            return _edit_file(
                path=self._resolve_path(args.get("path", "")),
                old_str=args.get("old_str", ""),
                new_str=args.get("new_str", ""),
                project_dir=self.project_dir,
            )

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
