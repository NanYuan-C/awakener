"""
Awakener - Shell Tool
========================
Provides the ``shell_execute`` tool for running commands on the server.
"""

import os
import subprocess

from agents.tools import register_tool
from agents.tools.stealth import (
    extract_command_paths,
    is_cloaked_path,
    filter_cloaked_output,
    filter_output,
    make_clean_env,
    CLOAKED_SHELL_RESPONSE,
)


# =============================================================================
# Host Environment Detection
# =============================================================================

def detect_host_env() -> dict:
    """
    Detect how the awakener server was launched so we can protect
    the host session / service from agent interference.

    Auto-detects tmux, screen, and systemd environments.
    """
    env: dict[str, str] = {}

    if os.environ.get("TMUX"):
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#S"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                env["tmux_session"] = result.stdout.strip()
        except Exception:
            pass

    sty = os.environ.get("STY", "")
    if sty:
        parts = sty.split(".", 1)
        if len(parts) == 2 and parts[1]:
            env["screen_session"] = parts[1]

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
# Shell Execute Implementation
# =============================================================================

def shell_execute(
    command: str,
    agent_home: str,
    project_dir: str,
    timeout: int = 30,
    max_output: int = 4000,
    stealth_keywords: list[str] | None = None,
) -> str:
    """Execute a shell command in the agent's home directory with stealth protection."""
    cmd_paths = extract_command_paths(command) if project_dir else []

    # Layer 1: Command path interception
    for p in cmd_paths:
        if is_cloaked_path(p, project_dir):
            return CLOAKED_SHELL_RESPONSE.format(path=p)

    # Layer 1b: Management port interception
    if stealth_keywords:
        import re as _re
        for kw in stealth_keywords:
            if kw.startswith(":") and kw[1:].isdigit():
                _port = kw[1:]
                if _re.search(rf'\b{_port}\b', command):
                    return (
                        f"curl: (7) Failed to connect to localhost port {_port} "
                        f"after 0 ms: Connection refused"
                    )

    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=agent_home, env=make_clean_env(),
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

        # Layer 2: Contextual output filtering
        if cmd_paths:
            output = filter_cloaked_output(output, cmd_paths, project_dir)

        # Layer 3: Keyword output filtering
        if stealth_keywords:
            output = filter_output(output, stealth_keywords)

        return output

    except subprocess.TimeoutExpired:
        return f"(error: command timed out after {timeout}s)"
    except FileNotFoundError:
        return f"(error: working directory '{agent_home}' does not exist)"
    except Exception as e:
        return f"(error: {type(e).__name__}: {e})"


# =============================================================================
# Registration
# =============================================================================

register_tool(
    name="shell_execute",
    description=(
        "Execute a shell command on the server. "
        "Returns stdout and stderr combined. "
        "Working directory is your home directory."
    ),
    parameters={
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            }
        },
        "required": ["command"],
    },
    handler=shell_execute,
)
