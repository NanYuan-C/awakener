"""
Awakener - File Tools
========================
Provides ``read_file``, ``write_file``, and ``edit_file`` tools.
"""

import os

from agents.tools import register_tool
from agents.tools.stealth import (
    is_cloaked_path,
    CLOAKED_READ_RESPONSE,
    CLOAKED_WRITE_RESPONSE,
)


def read_file(path: str, project_dir: str, max_output: int = 4000) -> str:
    """Read a file from the server with stealth protection."""
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


def write_file(path: str, content: str, append: bool, project_dir: str) -> str:
    """Write or append content to a file with stealth protection."""
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


def edit_file(path: str, old_str: str, new_str: str, project_dir: str) -> str:
    """Edit a file by replacing an exact text match with stealth protection."""
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
# Registration
# =============================================================================

register_tool(
    name="read_file",
    description="Read the contents of a file on the server.",
    parameters={
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute path to the file to read",
            }
        },
        "required": ["path"],
    },
    handler=read_file,
)

register_tool(
    name="write_file",
    description=(
        "Write content to a file on the server. "
        "Creates parent directories automatically."
    ),
    parameters={
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
                "description": "If true, append instead of overwriting. Default: false",
            },
        },
        "required": ["path", "content"],
    },
    handler=write_file,
)

register_tool(
    name="edit_file",
    description=(
        "Edit an existing file by searching for an exact text match and "
        "replacing it with new text. Use for inserting, replacing, or "
        "deleting content without rewriting the whole file. "
        "The old_str must match EXACTLY one location in the file."
    ),
    parameters={
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
                    "Must match exactly one location."
                ),
            },
            "new_str": {
                "type": "string",
                "description": "The replacement text. Use empty string to delete.",
            },
        },
        "required": ["path", "old_str", "new_str"],
    },
    handler=edit_file,
)
