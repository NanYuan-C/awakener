"""
Awakener - Agent Knowledge Base
==================================
Manages the agent's self-maintained knowledge base directory.

The knowledge base is the agent's long-term memory system — a directory
of files that the agent creates, organizes, and maintains on its own.
It follows the "progressive disclosure" pattern used by skills:

    knowledge/
      index.md      <- Catalog & usage guide (injected into prompt each round)
      ...           <- Any files the agent creates (read on demand)

How it works:
    1. On startup, the system ensures ``knowledge/`` and ``index.md`` exist.
    2. Each round, the content of ``index.md`` is read and injected into
       the system prompt. This gives the agent a concise map of everything
       it has stored, without loading all the details.
    3. The agent uses ``read_file`` / ``write_file`` to maintain the
       knowledge base. It can create any directory structure it wants.
    4. ``index.md`` has a character limit (configurable). If the file
       exceeds the limit, only the first N characters are injected,
       with a truncation warning. This forces the agent to keep the
       index concise and well-organized.

Why not a vector database?
    - The agent runs on minimal infrastructure (single server, no DB).
    - Plain files are transparent, debuggable, and editable by the admin.
    - The agent can develop its own organizational strategy over time.
    - A vector DB could be added later as a skill if needed.

Storage: {agent_home}/knowledge/
"""

import os

# =============================================================================
# Default index.md template
# =============================================================================

INDEX_TEMPLATE = """\
# Knowledge Base

This is your personal knowledge base. It persists across rounds.

## How to Use

- **This file (`index.md`) is injected into your prompt every round.**
  Keep it concise — it has a character limit.
- Use this file as a **catalog**: list what you know and where to find it.
- Create separate files in this directory for detailed content,
  then reference them here. Read them with `read_file` when needed.
- You are free to organize the directory however you want.

## Rules

- Keep `index.md` short and structured. If it exceeds the limit,
  the end will be truncated and you will lose information.
- Do NOT put large content directly in this file. Use references.
- Update this file at the end of each round to reflect what you learned.
""".lstrip()


# =============================================================================
# Knowledge Base Manager
# =============================================================================

def get_knowledge_dir(agent_home: str) -> str:
    """
    Return the absolute path to the agent's knowledge base directory.

    Args:
        agent_home: The agent's home directory path.

    Returns:
        Path to ``{agent_home}/knowledge/``.
    """
    return os.path.join(agent_home, "knowledge")


def ensure_knowledge_base(agent_home: str) -> str:
    """
    Ensure the knowledge base directory and index.md exist.

    If ``index.md`` does not exist, it is created from a minimal template.
    If it already exists (even if modified by the agent), it is left alone.

    Args:
        agent_home: The agent's home directory path.

    Returns:
        Absolute path to ``index.md``.
    """
    kb_dir = get_knowledge_dir(agent_home)
    os.makedirs(kb_dir, exist_ok=True)

    index_path = os.path.join(kb_dir, "index.md")
    if not os.path.exists(index_path):
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(INDEX_TEMPLATE)

    return index_path


def load_index(agent_home: str, max_chars: int = 2000) -> str:
    """
    Load the knowledge base index for prompt injection.

    Reads ``knowledge/index.md`` and returns its content, truncated
    to ``max_chars`` if necessary. A warning is appended when truncated
    so the agent knows it needs to trim the file.

    Args:
        agent_home: The agent's home directory path.
        max_chars:  Maximum characters to inject (default 2000).

    Returns:
        The index content string, or empty string if not found.
    """
    index_path = os.path.join(get_knowledge_dir(agent_home), "index.md")

    if not os.path.exists(index_path):
        return ""

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return ""

    if not content.strip():
        return ""

    if len(content) > max_chars:
        content = content[:max_chars] + (
            "\n\n⚠ [TRUNCATED — index.md exceeds the "
            f"{max_chars}-character limit. Trim it to avoid losing information.]"
        )

    return content
