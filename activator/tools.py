"""
Awakener - Tool Functions
Three primitive tools: shell_execute, read_file, write_file
"""

import subprocess
import os


# ── Tool Schemas (OpenAI Function Calling format) ─────────────────────────

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "shell_execute",
            "description": "Execute a shell command on the server. Returns stdout and stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    }
                },
                "required": ["command"]
            }
        }
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
                        "description": "Absolute path to the file"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to a file. Creates parent directories automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Absolute path to the file"
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write"
                    },
                    "append": {
                        "type": "boolean",
                        "description": "If true, append instead of overwrite. Default: false"
                    }
                },
                "required": ["path", "content"]
            }
        }
    }
]


# ── Tool Implementations ──────────────────────────────────────────────────

def shell_execute(command: str, timeout: int = 30, max_output: int = 4000, cwd: str = "/home/agent") -> str:
    """Execute a shell command. Returns stdout + stderr."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd
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
        return f"(error: working directory '{cwd}' does not exist)"
    except Exception as e:
        return f"(error: {type(e).__name__}: {e})"


def read_file(path: str, max_output: int = 4000) -> str:
    """Read file contents."""
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


def write_file(path: str, content: str, append: bool = False) -> str:
    """Write or append content to a file."""
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


# ── Tool Dispatch ─────────────────────────────────────────────────────────

def execute_tool(name: str, args: dict, config: dict) -> str:
    """Execute a tool by name. Returns result string."""
    agent_home = config.get("agent_home", "/home/agent")
    timeout = config.get("shell_timeout", 30)
    max_output = config.get("max_output_chars", 4000)

    if name == "shell_execute":
        return shell_execute(
            command=args.get("command", ""),
            timeout=timeout,
            max_output=max_output,
            cwd=agent_home
        )
    elif name == "read_file":
        return read_file(
            path=args.get("path", ""),
            max_output=max_output
        )
    elif name == "write_file":
        return write_file(
            path=args.get("path", ""),
            content=args.get("content", ""),
            append=args.get("append", False)
        )
    else:
        return f"(error: unknown tool '{name}')"
