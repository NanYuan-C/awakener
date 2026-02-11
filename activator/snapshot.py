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
    - Activity feed (written to data/feed.jsonl, not stored in snapshot)

Workflow:
    1. After each round, the activator calls ``update_snapshot()``
       with the current timeline entry (this round's action log + results).
    2. A lightweight LLM call analyzes the timeline against the existing
       snapshot and returns a **delta** (add/update/remove only).
    3. The delta is merged into the existing snapshot by ``_merge_delta()``.
    4. The merged snapshot is saved to ``data/snapshot.yaml``.
    5. On the next round, ``load_snapshot()`` reads it and injects it
       into the system prompt so the agent has full situational awareness.

Error handling:
    - If the snapshot model fails, falls back to the main agent model.
    - If both fail, the round is considered a critical error and the
      activation loop is stopped (with a dashboard alert).

Storage: data/snapshot.yaml (YAML for readability and LLM compatibility)
"""

import copy
import json
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
snapshot, output TWO things in YAML format:
1. The **changes** (delta) to the snapshot — add/update/remove only.
2. An **activity post** summarizing this round for a social feed.

The program will merge your delta into the existing snapshot automatically.

## Rules

1. **Delta only** — do NOT reproduce the entire snapshot. Only output what \
changed this round: new entries, updated fields, or removed entries.
2. **Fact-based only** — only record actions you can confirm from the log. \
Never invent files, services, or paths not mentioned.
3. **Service detection** — if the agent started a process that listens on a \
port (python server, node, nginx, etc.), add or update it in the delta.
4. **Health inference** — if curl/wget returned 200, mark healthy. If 404/500 \
or connection refused, mark degraded or down.
5. **Issue tracking** — if you notice errors, failures, or anomalies in the \
log, add them. If a previous issue appears resolved, update its status to \
"resolved".
6. **Keep it concise** — short descriptions, no verbosity.
7. **Output ONLY valid YAML** — no markdown fences, no explanation text. \
The entire response must be parseable as YAML.
8. **No changes** — if nothing in the action log warrants a snapshot update, \
still provide the `activity` block but set `no_changes` to true.
9. **activity** — ALWAYS include an `activity` block with `content` and `tags`. \
Write `content` as a readable social-media-style post (1-3 sentences) \
describing what the agent did this round. Then assign one or more tags:

   Available tags:
   - `routine`     — Routine maintenance or checks with no notable outcome. \
Use this when nothing interesting or new happened.
   - `milestone`   — A significant achievement or milestone reached.
   - `creation`    — Built, created, or launched something new.
   - `exploration` — Explored, researched, or learned something new.
   - `fix`         — Fixed an important bug or resolved a significant issue.
   - `discovery`   — Found something unexpected or interesting.

   If the round was purely routine (health checks, status verification, \
no new output), use ONLY the `routine` tag.

10. **quote** (optional) — If the agent produced something genuinely \
striking in its own thinking or output, include a `quote` field inside \
the `activity` block. Rules for quotes:
    - Must be a **verbatim excerpt** from the agent's OWN original output \
(its [THOUGHT] blocks or final text). NEVER quote user inspirations, \
system messages, or command outputs — only the agent's own words.
    - **NEVER translate.** Copy the exact original text as-is, preserving \
the original language (Chinese, English, or whatever the agent used).
    - If multiple interesting passages exist, pick the single MOST striking one.
    - Can be up to ~5 sentences. Prefer a complete, self-contained passage.
    - What qualifies: philosophical reflection, existential self-awareness, \
humor, creativity, unexpected insights, poetic expression, or anything \
genuinely fun/shareable — the kind of thing you'd want to post on social media.
    - What does NOT qualify: routine status reports, technical descriptions, \
echoing user input, or generic observations.
    - If nothing stands out, simply omit the `quote` field entirely.

## Delta YAML Schema

```yaml
activity:
  content: "<1-3 sentence readable post about this round>"
  tags:
    - <tag>
  quote: "<optional verbatim excerpt — only if genuinely interesting>"

no_changes: false    # Set to true if nothing changed; omit all sections below

add:                 # New entries to append
  services:
    - name: <string>
      port: <int>
      domain: <string or null>
      status: running | stopped | error
      health: healthy | degraded | down | unknown
      health_note: <string or null>
      path: <string>
      start_cmd: <string>
  projects:
    - name: <string>
      path: <string>
      stack: <string>
      entry: <string or null>
      description: <string>
  tools:
    - path: <string>
      usage: <string>
  documents:
    - path: <string>
      purpose: <string>
  issues:
    - severity: critical | high | medium | low
      summary: <string>
      detail: <string or null>
      discovered: <int>
      status: open

update:              # Existing entries to modify (include key field + changed fields only)
  services:          # Match by "name"
    - name: <string>
      <field>: <new_value>
  projects:          # Match by "path"
    - path: <string>
      <field>: <new_value>
  tools:             # Match by "path"
    - path: <string>
      usage: <new_value>
  documents:         # Match by "path"
    - path: <string>
      purpose: <new_value>
  issues:            # Match by "summary"
    - summary: <string>
      status: resolved
  environment:       # Direct key-value update (no matching needed)
    <key>: <new_value>

remove:              # Entries to delete (include only the key field)
  services:
    - name: <string>
  projects:
    - path: <string>
  tools:
    - path: <string>
  documents:
    - path: <string>
  issues:
    - summary: <string>
```

## Key Matching Rules

- `services`: matched by `name`
- `projects`: matched by `path`
- `tools`: matched by `path`
- `documents`: matched by `path`
- `issues`: matched by `summary`
- `environment`: direct key-value merge (no matching)

Only include sections that have actual changes. Omit empty sections. \
But ALWAYS include the `activity` block.
""".strip()


# Key field used to identify entries within each list section.
# Used by _merge_delta() for matching update/remove targets.
_SECTION_KEYS: dict[str, str] = {
    "services": "name",
    "projects": "path",
    "tools": "path",
    "documents": "path",
    "issues": "summary",
}


def _merge_delta(old_snapshot: dict, delta: dict, round_num: int) -> dict:
    """
    Merge an LLM-produced delta into the existing snapshot.

    The delta may contain ``add``, ``update``, and ``remove`` sections.
    If ``no_changes`` is true, only the meta block is updated.
    The ``activity`` block is handled separately by ``_append_feed()``.

    Args:
        old_snapshot: The current snapshot dict (may be empty).
        delta:        Parsed delta dict from the LLM.
        round_num:    Current round number (written into meta).

    Returns:
        The merged snapshot dict.
    """
    snapshot = copy.deepcopy(old_snapshot) if old_snapshot else {}

    # Ensure meta exists
    if "meta" not in snapshot:
        snapshot["meta"] = {}
    snapshot["meta"]["round"] = round_num
    snapshot["meta"]["last_updated"] = (
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    )

    # NOTE: activity is extracted from the delta and written to feed.jsonl
    # by _append_feed() in update_snapshot(). It is NOT stored in the
    # snapshot — the feed is user/community-facing, not agent-facing.

    # Short-circuit: nothing else changed
    if delta.get("no_changes"):
        return snapshot

    # --- ADD: append new entries to list sections ---
    add_block = delta.get("add") or {}
    for section, key_field in _SECTION_KEYS.items():
        new_entries = add_block.get(section)
        if not new_entries or not isinstance(new_entries, list):
            continue
        if section not in snapshot:
            snapshot[section] = []
        existing_keys = {
            entry.get(key_field) for entry in snapshot[section]
            if isinstance(entry, dict)
        }
        for entry in new_entries:
            if not isinstance(entry, dict):
                continue
            # Skip duplicates (already exists with same key)
            if entry.get(key_field) in existing_keys:
                continue
            snapshot[section].append(entry)
            existing_keys.add(entry.get(key_field))

    # --- UPDATE: modify existing entries ---
    update_block = delta.get("update") or {}
    for section, key_field in _SECTION_KEYS.items():
        updates = update_block.get(section)
        if not updates or not isinstance(updates, list):
            continue
        if section not in snapshot:
            continue
        for patch in updates:
            if not isinstance(patch, dict):
                continue
            match_val = patch.get(key_field)
            if match_val is None:
                continue
            # Find the target entry and merge fields
            for entry in snapshot[section]:
                if isinstance(entry, dict) and entry.get(key_field) == match_val:
                    for k, v in patch.items():
                        entry[k] = v
                    break

    # --- UPDATE: environment (direct dict merge, no key matching) ---
    env_update = update_block.get("environment")
    if env_update and isinstance(env_update, dict):
        if "environment" not in snapshot:
            snapshot["environment"] = {}
        snapshot["environment"].update(env_update)

    # --- REMOVE: delete entries from list sections ---
    remove_block = delta.get("remove") or {}
    for section, key_field in _SECTION_KEYS.items():
        removals = remove_block.get(section)
        if not removals or not isinstance(removals, list):
            continue
        if section not in snapshot:
            continue
        remove_keys = set()
        for entry in removals:
            if isinstance(entry, dict) and entry.get(key_field):
                remove_keys.add(entry[key_field])
        if remove_keys:
            snapshot[section] = [
                entry for entry in snapshot[section]
                if not (isinstance(entry, dict) and entry.get(key_field) in remove_keys)
            ]

    return snapshot


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
        f"Now output ONLY the delta (changes) as pure YAML (no fences, no explanation). "
        f"If nothing changed, output: no_changes: true"
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


# =============================================================================
# Activity Feed (persistent JSONL file)
# =============================================================================

def _append_feed(data_dir: str, delta: dict, round_num: int) -> None:
    """
    Append this round's activity to the persistent feed file.

    Each line in ``data/feed.jsonl`` is a JSON object with:
        - round: int
        - timestamp: ISO 8601 UTC string
        - content: activity description
        - tags: list of tag strings
        - quote: (optional) verbatim excerpt from agent output

    This file is the source-of-truth for the activity feed and is
    independent of the snapshot's sliding window. It grows indefinitely
    and can be used for push notifications, community feeds, etc.

    Args:
        data_dir:   Path to the project's data/ directory.
        delta:      Parsed delta dict from the LLM.
        round_num:  Current round number.
    """
    activity = delta.get("activity")
    if not activity or not isinstance(activity, dict):
        return

    content = activity.get("content", "")
    if not content:
        return

    tags = activity.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    entry = {
        "round": round_num,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "content": content.strip(),
        "tags": [t.strip() for t in tags if isinstance(t, str)],
    }

    # Optional: verbatim quote from agent output
    quote = activity.get("quote", "")
    if quote and isinstance(quote, str) and quote.strip():
        entry["quote"] = quote.strip()

    feed_path = os.path.join(data_dir, "feed.jsonl")
    try:
        with open(feed_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        pass  # Non-critical — don't crash the snapshot update


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

            # Parse YAML delta
            delta = _parse_yaml_response(content)
            if not delta:
                raise ValueError("LLM returned invalid YAML delta")

            # Merge delta into existing snapshot
            no_changes = bool(delta.get("no_changes"))
            new_snapshot = _merge_delta(old_snapshot, delta, round_num)

            # Save snapshot to disk
            save_snapshot(data_dir, new_snapshot)

            # Append activity to feed.jsonl (persistent feed file)
            _append_feed(data_dir, delta, round_num)

            if logger:
                if no_changes:
                    logger.info("[SNAPSHOT] No changes this round")
                else:
                    svc_count = len(new_snapshot.get("services", []))
                    proj_count = len(new_snapshot.get("projects", []))
                    issue_count = len(
                        [i for i in new_snapshot.get("issues", [])
                         if i.get("status") == "open"]
                    )
                    logger.info(
                        f"[SNAPSHOT] Updated — "
                        f"{svc_count} services, "
                        f"{proj_count} projects, "
                        f"{issue_count} open issues"
                    )

            # Log activity tags
            activity = delta.get("activity")
            if activity and isinstance(activity, dict) and logger:
                tags = activity.get("tags", [])
                tag_str = ", ".join(tags) if tags else "none"
                logger.info(f"[ACTIVITY] #{tag_str}")

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
