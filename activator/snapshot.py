"""
Awakener - System Snapshot Manager
=====================================
Maintains a structured asset inventory of the agent's server environment.
Updated automatically by an LLM "auditor" at the end of each activation round.

The snapshot captures:
    - Active services (ports, health, start commands)
    - Projects and directories the agent has created
    - Tools and scripts the agent has built
    - Important documents
    - System environment overview
    - Known issues discovered during the round

Workflow:
    1. After each round, the activator calls ``update_snapshot()``
       with the current timeline entry (this round's action log + results).
    2. A lightweight LLM call analyzes the timeline against the existing
       snapshot and returns an updated version.
    3. The new snapshot is saved to ``data/snapshot.yaml``.
    4. On the next round, ``load_snapshot()`` reads it and injects it
       into the system prompt so the agent has full situational awareness.

Error handling:
    - If the snapshot model fails, falls back to the main agent model.
    - If both fail, the round is considered a critical error and the
      activation loop is stopped (with a dashboard alert).

Storage: data/snapshot.yaml (YAML for readability and LLM compatibility)
"""

import os
import yaml
import litellm
from datetime import datetime, timezone
from typing import Any


# =============================================================================
# Snapshot File I/O
# =============================================================================

def _snapshot_path(data_dir: str) -> str:
    """Return the full path to the snapshot YAML file."""
    return os.path.join(data_dir, "snapshot.yaml")


def load_snapshot(data_dir: str) -> dict:
    """
    Load the current snapshot from disk.

    Returns an empty dict if the file doesn't exist or is corrupted.

    Args:
        data_dir: Path to the project's data/ directory.

    Returns:
        The snapshot dictionary, or empty dict.
    """
    path = _snapshot_path(data_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except (yaml.YAMLError, OSError):
        return {}


def save_snapshot(data_dir: str, snapshot: dict) -> None:
    """
    Save the snapshot to disk.

    Args:
        data_dir: Path to the project's data/ directory.
        snapshot: The snapshot dictionary to save.
    """
    path = _snapshot_path(data_dir)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            snapshot,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )


# =============================================================================
# Snapshot → Markdown Renderer (for prompt injection)
# =============================================================================

def render_snapshot_markdown(snapshot: dict) -> str:
    """
    Render the snapshot as a concise Markdown block for prompt injection.

    Designed to give the agent maximum situational awareness with
    minimum token usage.

    Args:
        snapshot: The snapshot dictionary.

    Returns:
        Markdown string, or empty string if snapshot is empty.
    """
    if not snapshot:
        return ""

    meta = snapshot.get("meta", {})
    lines = []
    lines.append(f"## System Snapshot (Round {meta.get('round', '?')})")
    lines.append("")

    # -- Services --
    services = snapshot.get("services", [])
    if services:
        lines.append("### Services")
        lines.append("| Name | Port | Status | Health | Path |")
        lines.append("|------|------|--------|--------|------|")
        for s in services:
            status = s.get("status", "unknown")
            health = s.get("health", "unknown")
            health_icon = {
                "healthy": "healthy",
                "degraded": "⚠ degraded",
                "down": "✖ down",
            }.get(health, health)
            lines.append(
                f"| {s.get('name', '?')} "
                f"| {s.get('port', '?')} "
                f"| {status} "
                f"| {health_icon} "
                f"| {s.get('path', '?')} |"
            )
        lines.append("")

    # -- Projects --
    projects = snapshot.get("projects", [])
    if projects:
        lines.append("### Projects")
        for p in projects:
            entry = p.get("entry", "")
            entry_str = f" → `{entry}`" if entry else ""
            lines.append(
                f"- **{p.get('name', '?')}**: "
                f"`{p.get('path', '?')}` "
                f"({p.get('stack', '?')}){entry_str}"
            )
            if p.get("description"):
                lines.append(f"  {p['description']}")
        lines.append("")

    # -- Tools --
    tools = snapshot.get("tools", [])
    if tools:
        lines.append("### Tools")
        for t in tools:
            lines.append(f"- `{t.get('path', '?')}` → {t.get('usage', '?')}")
        lines.append("")

    # -- Documents --
    documents = snapshot.get("documents", [])
    if documents:
        lines.append("### Documents")
        for d in documents:
            lines.append(f"- `{d.get('path', '?')}` — {d.get('purpose', '?')}")
        lines.append("")

    # -- Environment --
    env = snapshot.get("environment", {})
    if env:
        env_parts = []
        if env.get("os"):
            env_parts.append(f"OS: {env['os']}")
        if env.get("python"):
            env_parts.append(f"Python: {env['python']}")
        if env.get("domain"):
            ssl = " (SSL)" if env.get("ssl") else ""
            env_parts.append(f"Domain: {env['domain']}{ssl}")
        if env.get("disk_usage"):
            env_parts.append(f"Disk: {env['disk_usage']}")
        if env_parts:
            lines.append(f"### Environment: {' | '.join(env_parts)}")
            lines.append("")

    # -- Issues --
    issues = snapshot.get("issues", [])
    open_issues = [i for i in issues if i.get("status") == "open"]
    if open_issues:
        lines.append(f"### Issues ({len(open_issues)} open)")
        for i in open_issues:
            severity = i.get("severity", "?")
            icon = {"critical": "🔴", "high": "🟠", "medium": "⚠", "low": "ℹ"}.get(
                severity, "?"
            )
            lines.append(
                f"- {icon} {i.get('summary', '?')} (since R{i.get('discovered', '?')})"
            )
        lines.append("")

    return "\n".join(lines).strip()


# =============================================================================
# LLM-Based Snapshot Updater
# =============================================================================

SNAPSHOT_UPDATER_PROMPT = """\
You are a system auditor for an autonomous AI agent's Linux server.

Your job: given the agent's action log from this round and the current system \
snapshot, produce an UPDATED snapshot in YAML format.

## Rules

1. **Incremental update** — only modify what changed. Do not remove entries \
unless the agent explicitly deleted something.
2. **Fact-based only** — only record actions you can confirm from the log. \
Never invent files, services, or paths not mentioned.
3. **Service detection** — if the agent started a process that listens on a \
port (python server, node, nginx, etc.), add or update it in `services`.
4. **Health inference** — if curl/wget returned 200, mark healthy. If 404/500 \
or connection refused, mark degraded or down.
5. **Issue tracking** — if you notice errors, failures, or anomalies in the \
log, add them to `issues`. If a previous issue appears resolved, change its \
status to "resolved".
6. **Keep it concise** — short descriptions, no verbosity.
7. **Output ONLY valid YAML** — no markdown fences, no explanation text. \
The entire response must be parseable as YAML.

## YAML Schema

```yaml
meta:
  last_updated: "YYYY-MM-DD HH:MM:SS UTC"
  round: <int>

services:            # List of network services
  - name: <string>
    port: <int>
    domain: <string or null>
    status: running | stopped | error
    health: healthy | degraded | down | unknown
    health_note: <string or null>
    path: <string>             # Project/working directory
    start_cmd: <string>        # How to start/restart

projects:            # Directories the agent created/manages
  - name: <string>
    path: <string>
    stack: <string>            # e.g. "Python / FastAPI"
    entry: <string or null>    # Main entry file
    description: <string>

tools:               # Scripts/executables the agent created
  - path: <string>
    usage: <string>            # One-line usage hint

documents:           # Important files the agent maintains
  - path: <string>
    purpose: <string>

environment:
  os: <string or null>
  python: <string or null>
  domain: <string or null>
  ssl: <bool>
  disk_usage: <string or null>
  key_packages: [<string>, ...]

issues:              # Known problems
  - severity: critical | high | medium | low
    summary: <string>
    detail: <string or null>
    discovered: <int>          # Round number
    status: open | resolved
```
""".strip()


def _build_updater_messages(
    old_snapshot: dict,
    timeline_entry: dict,
    round_num: int,
) -> list[dict]:
    """
    Build the messages for the snapshot updater LLM call.

    Args:
        old_snapshot:   The current snapshot dict (may be empty).
        timeline_entry: This round's timeline entry (action_log used).
        round_num:      Current round number.

    Returns:
        Messages list for litellm.completion().
    """
    # Serialize old snapshot
    if old_snapshot:
        old_yaml = yaml.dump(
            old_snapshot,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    else:
        old_yaml = "(empty — this is the first snapshot)"

    # Build the action log from the timeline entry
    # Only the action_log (tool-calling steps) is sent — the final summary
    # is excluded because it adds noise without useful structural info.
    action_log = timeline_entry.get("action_log", "")
    tools_used = timeline_entry.get("tools_used", 0)
    duration = timeline_entry.get("duration", 0)

    user_content = (
        f"## Current Snapshot\n\n"
        f"```yaml\n{old_yaml}```\n\n"
        f"## Round {round_num} Action Log "
        f"(Tools: {tools_used}, Duration: {duration}s)\n\n"
        f"{action_log}\n\n"
        f"---\n\n"
        f"Now output the UPDATED snapshot as pure YAML (no fences, no explanation)."
    )

    return [
        {"role": "system", "content": SNAPSHOT_UPDATER_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _parse_yaml_response(text: str) -> dict | None:
    """
    Parse YAML from the LLM response, stripping any markdown fences.

    Args:
        text: Raw LLM response text.

    Returns:
        Parsed dict, or None if parsing failed.
    """
    if not text:
        return None

    # Strip markdown code fences if present
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (```yaml or ```)
        first_newline = cleaned.index("\n") if "\n" in cleaned else len(cleaned)
        cleaned = cleaned[first_newline + 1:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    cleaned = cleaned.strip()
    if not cleaned:
        return None

    try:
        data = yaml.safe_load(cleaned)
        return data if isinstance(data, dict) else None
    except yaml.YAMLError:
        return None


class SnapshotUpdateError(Exception):
    """Raised when snapshot update fails on both models."""
    pass


def update_snapshot(
    data_dir: str,
    timeline_entry: dict,
    round_num: int,
    snapshot_model: str | None,
    main_model: str,
    api_key: str | None = None,
    logger: Any = None,
) -> dict:
    """
    Update the system snapshot using an LLM auditor.

    Calls the snapshot_model (or main_model if not configured) to analyze
    this round's timeline and update the snapshot. On failure, falls back
    to the main_model. If both fail, raises SnapshotUpdateError.

    Args:
        data_dir:       Path to the project's data/ directory.
        timeline_entry: This round's timeline dict (from MemoryManager).
        round_num:      Current round number.
        snapshot_model:  LiteLLM model ID for the auditor (may be None).
        main_model:     Main agent model ID (fallback).
        api_key:        API key (used for both models unless different).
        logger:         ActivatorLogger instance for status updates.

    Returns:
        The updated snapshot dict.

    Raises:
        SnapshotUpdateError: If both model calls fail.
    """
    old_snapshot = load_snapshot(data_dir)
    messages = _build_updater_messages(old_snapshot, timeline_entry, round_num)

    # Determine which models to try
    primary = snapshot_model or main_model
    fallback = main_model if (snapshot_model and snapshot_model != main_model) else None

    models_to_try = [primary]
    if fallback:
        models_to_try.append(fallback)

    last_error = None

    for i, model in enumerate(models_to_try):
        is_fallback = i > 0
        label = "fallback model" if is_fallback else "snapshot model"

        if logger:
            if is_fallback:
                logger.info(f"[SNAPSHOT] Fallback to main model: {model}")
            else:
                logger.info(f"[SNAPSHOT] Updating snapshot with {model}")

        try:
            # Resolve API key for this model
            model_key = _resolve_snapshot_api_key(model, api_key)

            response = litellm.completion(
                model=model,
                messages=messages,
                api_key=model_key,
                stream=False,
                temperature=0.1,  # Low temperature for factual output
            )

            content = response.choices[0].message.content or ""

            # Parse YAML
            new_snapshot = _parse_yaml_response(content)
            if not new_snapshot:
                raise ValueError("LLM returned invalid YAML")

            # Ensure meta is up to date
            if "meta" not in new_snapshot:
                new_snapshot["meta"] = {}
            new_snapshot["meta"]["last_updated"] = (
                datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            )
            new_snapshot["meta"]["round"] = round_num

            # Save to disk
            save_snapshot(data_dir, new_snapshot)

            if logger:
                svc_count = len(new_snapshot.get("services", []))
                proj_count = len(new_snapshot.get("projects", []))
                issue_count = len(
                    [i for i in new_snapshot.get("issues", []) if i.get("status") == "open"]
                )
                logger.info(
                    f"[SNAPSHOT] Updated — "
                    f"{svc_count} services, "
                    f"{proj_count} projects, "
                    f"{issue_count} open issues"
                )

            return new_snapshot

        except Exception as e:
            last_error = e
            if logger:
                logger.info(
                    f"[SNAPSHOT] {label} failed: {type(e).__name__}: {e}"
                )
            continue

    # Both models failed
    raise SnapshotUpdateError(
        f"Snapshot update failed on all models. Last error: {last_error}"
    )


# =============================================================================
# Helper: Resolve API Key for Snapshot Model
# =============================================================================

def _resolve_snapshot_api_key(model: str, default_key: str | None) -> str | None:
    """
    Resolve the API key for the snapshot model.

    If the snapshot model uses a different provider than the main model,
    we need to look up the correct environment variable.

    Args:
        model:       LiteLLM model identifier.
        default_key: The main agent's API key (fallback).

    Returns:
        API key string, or None.
    """
    provider = model.split("/")[0].upper() if "/" in model else model.upper()

    key_map = {
        "DEEPSEEK": "DEEPSEEK_API_KEY",
        "OPENAI": "OPENAI_API_KEY",
        "ANTHROPIC": "ANTHROPIC_API_KEY",
        "GOOGLE": "GOOGLE_API_KEY",
        "GEMINI": "GOOGLE_API_KEY",
        "OPENROUTER": "OPENROUTER_API_KEY",
    }

    env_name = key_map.get(provider)
    if env_name:
        key = os.environ.get(env_name)
        if key:
            return key

    return default_key
