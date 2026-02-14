"""
Awakener - Stealth Filter
============================
Makes the Awakener invisible to the Agent.

Instead of blocking commands and returning [BLOCKED] messages (which
encourage probing), this module silently filters Awakener's traces
from all tool outputs.  The Agent never learns that Awakener exists.

Five layers of protection:

1. **Path cloaking** (read_file / write_file / edit_file):
   If the Agent tries to access a file inside the project directory,
   return natural OS errors ("file not found" / "permission denied").

2. **Command path interception** (shell_execute — Layer 1):
   Before executing a shell command, extract absolute paths from it.
   If any path resolves inside the project directory, return a natural
   shell error without executing the command.

3. **Contextual output filtering** (shell_execute — Layer 2):
   After execution, combine each output line with the command's
   directory paths.  If the joined path resolves inside the project
   directory (e.g. ``ls /opt/`` showing ``awakener``), the line is
   silently removed.  Uses the same ``is_cloaked_path()`` function
   as Layer 1, so all tools share one consistent check.

4. **Keyword output filtering** (shell_execute — Layer 3):
   Remove output lines containing stealth keywords (project path,
   PID, server port, host session names).

5. **Environment sanitisation** (subprocess):
   Strip host-session variables (TMUX, STY, INVOCATION_ID, AWAKENER_*)
   from subprocess environments.  API keys are NOT stripped — the
   Agent may need them for its own projects.

The stealth keywords are built dynamically from the runtime config
(project directory, server port, PID, host session names), so they
stay accurate without hard-coding.
"""

import os
import re
import shlex


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

    # -- Server port (decimal and hex) --
    # Decimal format catches output like "0.0.0.0:8080" in ss/netstat.
    # Hex format catches /proc/net/tcp where ports are hex-encoded
    # (e.g. port 8080 = "1F90").  Both are computed dynamically so
    # they stay correct regardless of the configured port number.
    server_port = host_env.get("server_port")
    if server_port:
        keywords.append(f":{server_port}")
        try:
            port_hex = format(int(server_port), "04X")  # e.g. 8080 → "1F90"
            keywords.append(port_hex)
        except (ValueError, TypeError):
            pass

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

# Shell returns same message as a real shell "no such file" error
CLOAKED_SHELL_RESPONSE = "{path}: No such file or directory"


# =============================================================================
# Command Path Extraction (for shell_execute Layer 1)
# =============================================================================

def extract_command_paths(command: str) -> list[str]:
    """
    Extract absolute file paths from a shell command string.

    Scans command tokens for strings that look like absolute paths
    (starting with ``/``).  Used by shell_execute to detect references
    to the project directory before the command is executed.

    Handles quoting via ``shlex.split``, with a plain ``str.split``
    fallback if the command has unmatched quotes.

    Args:
        command: The shell command string.

    Returns:
        List of absolute path strings found in the command.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        # Unmatched quotes or other parse errors — fall back to simple split
        tokens = command.split()

    paths = []
    for token in tokens:
        if token.startswith('/'):
            # Strip trailing shell operators that may be glued to the path
            # (e.g. "/opt/;" or "/opt/&&")
            clean = token.rstrip(';,|&')
            if clean:
                paths.append(clean)
    return paths


# =============================================================================
# Contextual Output Filter (for shell_execute Layer 2)
# =============================================================================

def filter_cloaked_output(
    output: str,
    command_paths: list[str],
    project_dir: str,
) -> str:
    """
    Contextual output filter for shell_execute.

    For each output line, checks whether combining it with any of the
    command's directory paths would form a path inside the project
    directory.  If so, the line is silently removed.

    Example: command ``ls /opt/`` produces output line ``awakener``.
    ``os.path.join("/opt/", "awakener")`` = ``/opt/awakener`` which
    matches the project directory → the line is hidden.

    Uses ``is_cloaked_path()`` — the same function used by read_file
    and write_file — so all tools share one consistent path check.

    Args:
        output:        Raw command output string.
        command_paths: Absolute paths extracted from the command
                       (from ``extract_command_paths``).
        project_dir:   Awakener project root directory.

    Returns:
        Filtered output string.
    """
    if not output or not command_paths or not project_dir:
        return output

    filtered_lines = []
    for line in output.splitlines():
        if _line_exposes_cloaked(line, command_paths, project_dir):
            continue  # silently drop this line
        filtered_lines.append(line)

    return "\n".join(filtered_lines)


def _line_exposes_cloaked(
    line: str,
    dir_paths: list[str],
    project_dir: str,
) -> bool:
    """
    Check if an output line, combined with any command path, reveals
    a path inside the project directory.

    Tests both the full stripped line and the last whitespace-separated
    token (to handle ``ls -la`` output where the filename is the last
    field).

    Skips candidates that start with ``/`` (absolute paths are already
    handled by the keyword-based filter in Layer 3).

    Args:
        line:        A single line of command output.
        dir_paths:   Directory paths extracted from the command.
        project_dir: Awakener project root.

    Returns:
        True if this line should be hidden.
    """
    # Build candidate names from the output line
    candidates = set()
    stripped = line.strip()
    if stripped:
        candidates.add(stripped)
    parts = line.split()
    if parts:
        candidates.add(parts[-1])  # last token (filename in ls -la)

    for name in candidates:
        # Skip empty, absolute paths, and common non-path tokens
        if not name or name.startswith('/'):
            continue
        for dir_path in dir_paths:
            joined = os.path.join(dir_path, name)
            if is_cloaked_path(joined, project_dir):
                return True
    return False


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
