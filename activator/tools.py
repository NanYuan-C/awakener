"""
Awakener - Agent Tool Set
============================
Defines the 5 tools available to the autonomous agent:

    1. shell_execute  - Run a shell command (cwd = agent_home)
    2. read_file      - Read a file from the server
    3. write_file     - Write/append content to a file
    4. notebook_write - Save this round's note (mandatory each round)
    5. notebook_read  - Read ONE specific historical round's note

Safety:
    - The awakener project directory is a FORBIDDEN ZONE.
      Any file operation or shell command that targets the project
      directory will be blocked with an error message.
    - The agent cannot kill its own activator process.
    - All file paths are resolved to absolute paths before checking.
"""

import os
import re
import subprocess
from typing import Any


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
]


# =============================================================================
# Safety Constants
# =============================================================================

BLOCKED_MSG = (
    "[BLOCKED] This path is in the system restricted zone. "
    "You cannot access the awakener project files."
)

BLOCKED_KILL_MSG = (
    "[BLOCKED] You cannot terminate the awakener process. "
    "This is a system-protected operation."
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


def _is_shell_command_forbidden(command: str, project_dir: str, activator_pid: int | None) -> str | None:
    """
    Check if a shell command attempts to access the project directory
    or kill the activator process.

    Returns an error message string if blocked, or None if allowed.

    Checks performed:
        1. Command contains the project directory path (cd, cat, ls, rm, etc.)
        2. Command tries to kill the activator PID
        3. Command tries to kill parent processes indiscriminately

    Args:
        command:       The shell command string to check.
        project_dir:   The awakener project root (forbidden zone).
        activator_pid: PID of the current activator process.

    Returns:
        Error message if the command is blocked, None if safe.
    """
    # Normalize project dir for string matching
    norm_dir = os.path.realpath(os.path.abspath(project_dir))

    # Check if command references the project directory
    # We check both the normalized path and the original config path
    paths_to_check = {norm_dir, project_dir}
    for p in paths_to_check:
        if p in command:
            return BLOCKED_MSG

    # Check for process killing commands targeting our PID
    if activator_pid is not None:
        # Patterns like: kill 12345, kill -9 12345, pkill -P 12345
        kill_patterns = [
            rf"\bkill\b.*\b{activator_pid}\b",
            rf"\bpkill\b.*-P\s*{activator_pid}\b",
        ]
        for pattern in kill_patterns:
            if re.search(pattern, command):
                return BLOCKED_KILL_MSG

    # Block "kill -9 -1" or similar mass-kill commands
    if re.search(r"\bkill\b.*-\d+\s+-1\b", command):
        return BLOCKED_KILL_MSG

    return None


# =============================================================================
# Tool Implementations
# =============================================================================

def _shell_execute(
    command: str,
    agent_home: str,
    project_dir: str,
    activator_pid: int | None,
    timeout: int = 30,
    max_output: int = 4000,
) -> str:
    """
    Execute a shell command in the agent's home directory.

    Safety checks are performed before execution:
    - The command cannot reference the awakener project directory.
    - The command cannot kill the activator process.

    Args:
        command:       Shell command string.
        agent_home:    Agent's working directory (cwd for subprocess).
        project_dir:   Awakener project root (forbidden zone).
        activator_pid: PID of the activator process.
        timeout:       Max execution time in seconds.
        max_output:    Max characters to return.

    Returns:
        Command output or error message.
    """
    # Safety check
    blocked = _is_shell_command_forbidden(command, project_dir, activator_pid)
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
) -> str:
    """
    Read a file from the server.

    Args:
        path:        Absolute path to the file.
        project_dir: Awakener project root (forbidden zone).
        max_output:  Max characters to return.

    Returns:
        File content or error message.
    """
    if _is_path_forbidden(path, project_dir):
        return BLOCKED_MSG

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

    Args:
        path:        Absolute path to the file.
        content:     Text content to write.
        append:      If True, append instead of overwrite.
        project_dir: Awakener project root (forbidden zone).

    Returns:
        Success message or error.
    """
    if _is_path_forbidden(path, project_dir):
        return BLOCKED_MSG

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
    ):
        self.agent_home = agent_home
        self.project_dir = project_dir
        self.activator_pid = activator_pid
        self.timeout = timeout
        self.max_output = max_output
        self.memory = memory_manager
        self.current_round = current_round
        self.notebook_written = False

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
                activator_pid=self.activator_pid,
                timeout=self.timeout,
                max_output=self.max_output,
            )

        elif name == "read_file":
            return _read_file(
                path=args.get("path", ""),
                project_dir=self.project_dir,
                max_output=self.max_output,
            )

        elif name == "write_file":
            return _write_file(
                path=args.get("path", ""),
                content=args.get("content", ""),
                append=args.get("append", False),
                project_dir=self.project_dir,
            )

        elif name == "notebook_write":
            return self._notebook_write(args.get("content", ""))

        elif name == "notebook_read":
            return self._notebook_read(args.get("round", 0))

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
