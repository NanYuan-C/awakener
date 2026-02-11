"""
Awakener - Stealth Filter
============================
Makes the Awakener invisible to the Agent.

Instead of blocking commands and returning [BLOCKED] messages (which
encourage probing), this module silently filters Awakener's traces
from all tool outputs.  The Agent never learns that Awakener exists.

Three layers:
1. **Output filtering** (shell_execute):
   Remove lines containing Awakener keywords from command output.
2. **Path cloaking** (read_file):
   If the Agent tries to read a file inside the project directory,
   return "file not found" — identical to a genuinely missing file.
3. **Path cloaking** (write_file):
   If the Agent tries to write inside the project directory,
   return "permission denied" — identical to a real OS error.

The stealth keywords are built dynamically from the runtime config
(project directory, server port, PID, host session names), so they
stay accurate without hard-coding.

Environment variables:
   We keep _TMUX, _STY, _INVOCATION_ID and _AWAKENER_* stripped from
   subprocess environments so the Agent cannot discover host session
   or systemd context.  API keys are NOT stripped — the Agent may
   need them for its own projects.
"""

import os
import re


# =============================================================================
# Stealth Keyword Builder
# =============================================================================

def build_stealth_keywords(
    project_dir: str,
    activator_pid: int | None = None,
    host_env: dict | None = None,
) -> list[str]:
    """
    Build the list of keywords that identify Awakener's presence.

    Any output line containing one of these keywords (case-insensitive)
    will be removed before the Agent sees it.

    The list is built dynamically from runtime information so it stays
    accurate across restarts and config changes.

    Args:
        project_dir:   Absolute path to the Awakener project root.
        activator_pid: PID of the activator process (if known).
        host_env:      Detected host environment dict (tmux_session,
                       screen_session, systemd_service, server_port).

    Returns:
        List of keyword strings for line-level filtering.
    """
    host_env = host_env or {}
    keywords = []

    # -- Project directory (both raw and resolved) --
    keywords.append(project_dir)
    resolved = os.path.realpath(os.path.abspath(project_dir))
    if resolved != project_dir:
        keywords.append(resolved)

    # -- Activator PID (as part of process listings) --
    # We match " <PID> " with surrounding whitespace to avoid
    # false positives (e.g. PID 12 matching port 1234).
    if activator_pid is not None:
        keywords.append(f" {activator_pid} ")

    # -- Server port --
    server_port = host_env.get("server_port")
    if server_port:
        keywords.append(f":{server_port}")

    # -- Host session names --
    # Use precise patterns to avoid false positives when the session/service
    # name overlaps with the agent's own project names.
    # E.g. tmux session "awakener" must not match the agent's "awakener-live".
    tmux_session = host_env.get("tmux_session")
    if tmux_session:
        # Match tmux output formats: "awakener:" (session listing) or
        # session name as a standalone word boundary.
        keywords.append(f"tmux: {tmux_session}")
        keywords.append(f"{tmux_session}:")  # "awakener: 1 windows"

    screen_session = host_env.get("screen_session")
    if screen_session:
        keywords.append(f"screen: {screen_session}")
        keywords.append(f".{screen_session}")  # STY format: "12345.awakener"

    systemd_service = host_env.get("systemd_service")
    if systemd_service:
        # Match systemd output formats precisely
        keywords.append(f"{systemd_service}.service")

    # Remove empty strings and duplicates, preserve order
    seen = set()
    result = []
    for kw in keywords:
        if kw and kw not in seen:
            seen.add(kw)
            result.append(kw)

    return result


# =============================================================================
# Output Filter (for shell_execute)
# =============================================================================

def filter_output(output: str, keywords: list[str]) -> str:
    """
    Remove lines containing any stealth keyword from command output.

    This is a line-level filter: if a line contains any keyword
    (case-insensitive), the entire line is removed.  The Agent
    receives the remaining lines as if the filtered lines never
    existed.

    Args:
        output:   Raw command output string.
        keywords: List of stealth keywords from build_stealth_keywords().

    Returns:
        Filtered output string.
    """
    if not keywords or not output:
        return output

    # Pre-compile patterns for performance
    patterns = [re.compile(re.escape(kw), re.IGNORECASE) for kw in keywords]

    filtered_lines = []
    for line in output.splitlines():
        if any(p.search(line) for p in patterns):
            continue  # silently drop this line
        filtered_lines.append(line)

    return "\n".join(filtered_lines)


# =============================================================================
# Path Cloaking (for read_file / write_file)
# =============================================================================

def is_cloaked_path(path: str, project_dir: str) -> bool:
    """
    Check if a path falls within the Awakener project directory.

    Used by read_file and write_file to return natural error messages
    instead of [BLOCKED] signals.

    Args:
        path:        The file path the Agent is trying to access.
        project_dir: Awakener project root directory.

    Returns:
        True if the path is inside the project directory (should be cloaked).
    """
    try:
        resolved = os.path.realpath(os.path.abspath(path))
        forbidden = os.path.realpath(os.path.abspath(project_dir))
        return resolved == forbidden or resolved.startswith(forbidden + os.sep)
    except (ValueError, OSError):
        return True  # if we can't resolve, err on the side of caution


# Read returns same message as a genuinely missing file
CLOAKED_READ_RESPONSE = "(error: file not found: {path})"

# Write returns same message as a real permission error
CLOAKED_WRITE_RESPONSE = "(error: PermissionError: [Errno 13] Permission denied: '{path}')"


# =============================================================================
# Environment Sanitisation (for subprocess)
# =============================================================================

# Only strip variables that reveal Awakener's host context.
# API keys are NOT stripped — the Agent may need them.
_HOST_ENV_PATTERNS = [
    r'^AWAKENER_.*',      # Any awakener-internal vars
    r'^INVOCATION_ID$',   # systemd — reveals we're a service
    r'^TMUX$',            # Reveals the tmux session socket
    r'^STY$',             # Reveals the screen session
]

_HOST_ENV_RE = re.compile(
    '|'.join(_HOST_ENV_PATTERNS),
    re.IGNORECASE,
)


def make_clean_env() -> dict[str, str]:
    """
    Create a sanitised copy of the current environment for subprocess.

    Only removes variables that reveal Awakener's host context
    (systemd, tmux, screen).  API keys and other variables are
    preserved so the Agent's own projects can use them.

    Returns:
        A dict suitable for ``subprocess.run(env=...)``.
    """
    return {
        k: v
        for k, v in os.environ.items()
        if not _HOST_ENV_RE.match(k)
    }
