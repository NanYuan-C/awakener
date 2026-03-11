"""
Awakener - Unified LLM Client
================================
Wraps litellm for all LLM calls across the project.
Provides API key resolution, JSON repair for broken tool arguments,
and a shared interface used by the agent engine and auditor.
"""

import json
import os
import re


# =============================================================================
# API Key Resolution
# =============================================================================

def resolve_api_key(model: str) -> str | None:
    """
    Resolve the API key from environment variables based on model provider.

    The model format is "provider/model-name", e.g. "deepseek/deepseek-chat".

    Returns:
        API key string, or None (LiteLLM will try env vars itself).
    """
    provider = model.split("/")[0].upper() if "/" in model else model.upper()

    key_map = {
        "DEEPSEEK": "DEEPSEEK_API_KEY",
        "OPENAI": "OPENAI_API_KEY",
        "ANTHROPIC": "ANTHROPIC_API_KEY",
        "GOOGLE": "GOOGLE_API_KEY",
        "GEMINI": "GOOGLE_API_KEY",
        "MINIMAX": "MINIMAX_API_KEY",
    }

    env_name = key_map.get(provider)
    if env_name:
        return os.environ.get(env_name)

    # Fallback: try {PROVIDER}_API_KEY for any unknown provider
    fallback_env = f"{provider}_API_KEY"
    val = os.environ.get(fallback_env)
    if val:
        return val

    return None


# =============================================================================
# JSON Repair for LLM Tool Arguments
# =============================================================================

def repair_json(raw: str) -> dict | None:
    """
    Attempt to repair broken JSON from LLM tool-call arguments.

    LLMs often produce invalid JSON when generating large payloads.
    Common failure modes:
      1. Truncated output (missing closing quotes/braces)
      2. Unescaped control characters inside strings
      3. Invalid escape sequences (e.g. \\x, \\0)

    Returns:
        Parsed dict if repair succeeded, None if all attempts failed.
    """
    if not raw or not raw.strip():
        return None

    # Attempt 1: Fix invalid escape sequences
    fixed = re.sub(r'\\([^"\\/bfnrtu])', r'\1', raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # Attempt 2: Close truncated JSON
    repaired = fixed.rstrip()

    in_string = False
    i = 0
    while i < len(repaired):
        c = repaired[i]
        if c == '\\' and in_string:
            i += 2
            continue
        if c == '"':
            in_string = not in_string
        i += 1

    if in_string:
        repaired += '"'

    open_braces = repaired.count('{') - repaired.count('}')
    open_brackets = repaired.count('[') - repaired.count(']')

    repaired += ']' * max(0, open_brackets)
    repaired += '}' * max(0, open_braces)

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # Attempt 3: Extract key fields with regex (last resort)
    path_match = re.search(r'"path"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    content_match = re.search(r'"content"\s*:\s*"((?:[^"\\]|\\.)*)', raw)
    append_match = re.search(r'"append"\s*:\s*(true|false)', raw)

    if path_match and content_match:
        result = {
            "path": path_match.group(1).encode().decode('unicode_escape', errors='replace'),
            "content": content_match.group(1).encode().decode('unicode_escape', errors='replace'),
        }
        if append_match:
            result["append"] = append_match.group(1) == "true"
        return result

    cmd_match = re.search(r'"command"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    if cmd_match:
        return {"command": cmd_match.group(1).encode().decode('unicode_escape', errors='replace')}

    if content_match and not path_match:
        return {
            "content": content_match.group(1).encode().decode('unicode_escape', errors='replace'),
        }

    return None
