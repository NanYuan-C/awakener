"""
Awakener - Agent Core (Single Round)
=======================================
Runs one activation round: calls the LLM via LiteLLM, dispatches tool
calls, and enforces the tool budget.

The round lifecycle:
    1. Build system + user messages (done by caller)
    2. Enter the tool-calling loop (streaming)
    3. LLM streams response -> broadcast thoughts in real-time
    4. Collect tool_calls from stream -> execute one by one
    5. Repeat until LLM stops calling tools or budget exhausted
    6. Extract round summary for timeline

Streaming:
    LLM responses are streamed (stream=True) so that:
    - Agent thoughts appear on the dashboard in real-time
    - Tool calls are broadcast before execution begins
    - Tool results are broadcast immediately after execution
    This eliminates the "everything appears at once" problem.

Budget enforcement:
    - normal_limit: Max tool calls the agent can use freely
    - hard_limit (normal + 3): force stop

DeepSeek reasoner support:
    - reasoning_content from the response is preserved in the
      conversation history so the model doesn't lose its thinking chain.
"""

import json
import re
from datetime import datetime
from typing import Callable

import litellm
from activator.tools import ToolExecutor, TOOLS_SCHEMA, get_tools_schema


# =============================================================================
# JSON Repair for LLM Tool Arguments
# =============================================================================

def _repair_json(raw: str) -> dict | None:
    """
    Attempt to repair broken JSON from LLM tool-call arguments.

    LLMs often produce invalid JSON when generating large payloads
    (e.g. writing a full CSS/HTML file). Common failure modes:

    1. Truncated output (missing closing quotes/braces)
    2. Unescaped control characters inside strings
    3. Invalid escape sequences (e.g. \\x, \\0)

    This function tries progressively more aggressive repairs.

    Args:
        raw: The raw JSON string that failed json.loads().

    Returns:
        Parsed dict if repair succeeded, None if all attempts failed.
    """
    if not raw or not raw.strip():
        return None

    # -- Attempt 1: Fix invalid escape sequences --
    # Replace common bad escapes: \x, \0, \a, etc. with their literal chars
    fixed = re.sub(r'\\([^"\\/bfnrtu])', r'\1', raw)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    # -- Attempt 2: Close truncated JSON --
    # The LLM often gets cut off mid-string, leaving unclosed quotes/braces.
    # Strategy: close any open string, then close open braces.
    repaired = fixed.rstrip()

    # If we're inside an unclosed string, close it
    # Count unescaped quotes
    in_string = False
    i = 0
    while i < len(repaired):
        c = repaired[i]
        if c == '\\' and in_string:
            i += 2  # Skip escaped char
            continue
        if c == '"':
            in_string = not in_string
        i += 1

    if in_string:
        repaired += '"'

    # Close any unclosed braces/brackets
    open_braces = repaired.count('{') - repaired.count('}')
    open_brackets = repaired.count('[') - repaired.count(']')

    repaired += ']' * max(0, open_brackets)
    repaired += '}' * max(0, open_braces)

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        pass

    # -- Attempt 3: Extract key fields with regex --
    # Last resort for write_file: extract path and content directly
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

    # For other tools: try extracting "command" field
    cmd_match = re.search(r'"command"\s*:\s*"((?:[^"\\]|\\.)*)"', raw)
    if cmd_match:
        return {"command": cmd_match.group(1).encode().decode('unicode_escape', errors='replace')}

    # Fallback: try extracting "content" field
    if content_match and not path_match:
        return {
            "content": content_match.group(1).encode().decode('unicode_escape', errors='replace'),
        }

    return None


# =============================================================================
# Round Result Data Class
# =============================================================================

class RoundResult:
    """
    Holds the outcome of a single activation round.

    Attributes:
        tools_used:     Total tool calls made this round.
        summary:        Full text summary (for timeline page display).
        action_log:     Concise action log — only the brief thoughts from
                        turns that triggered tool calls (for prompt injection).
        error:          Error message if the round failed, else None.
    """

    def __init__(
        self,
        tools_used: int = 0,
        summary: str = "",
        action_log: str = "",
        error: str | None = None,
    ):
        self.tools_used = tools_used
        self.summary = summary
        self.action_log = action_log
        self.error = error


# =============================================================================
# Summary Extraction
# =============================================================================

def _extract_summary(messages: list[dict]) -> str:
    """
    Extract a full summary from the agent's messages this round.

    Collects reasoning_content and content from assistant messages,
    skipping tool calls and tool results. Each section is prefixed
    with its timestamp (if available) for timeline display.

    No truncation — the complete thought process is preserved.

    Args:
        messages: Full conversation history for this round.

    Returns:
        A text summary of the agent's thoughts and outputs, with
        time prefixes like ``[15:04:18] [Thinking] ...``.
    """
    parts = []
    for msg in messages:
        if msg.get("role") == "assistant":
            ts = msg.get("_timestamp", "")
            prefix = f"[{ts}] " if ts else ""
            if msg.get("reasoning_content"):
                parts.append(f"{prefix}[Thinking] {msg['reasoning_content']}")
            if msg.get("content"):
                parts.append(f"{prefix}{msg['content']}")

    full_text = "\n".join(parts).strip()
    if not full_text:
        full_text = "(no text output this round)"

    return full_text


def _extract_action_log(messages: list[dict]) -> str:
    """
    Extract a concise action log from "working" assistant messages.

    Only includes assistant messages that triggered tool calls — the brief
    thoughts the agent had between tool executions.  The final assistant
    message (which has no tool_calls and is typically a long summary) is
    excluded because the summary already captures that information.

    This action log is injected into the next round's prompt so the agent
    can see *what it did* without the redundant summary.

    Args:
        messages: Full conversation history for this round.

    Returns:
        A concise, time-prefixed action log.
    """
    parts = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        # Only include turns that triggered tool calls
        if not msg.get("tool_calls"):
            continue
        ts = msg.get("_timestamp", "")
        prefix = f"[{ts}] " if ts else ""
        if msg.get("reasoning_content"):
            parts.append(f"{prefix}[Thinking] {msg['reasoning_content']}")
        if msg.get("content"):
            parts.append(f"{prefix}{msg['content']}")

    return "\n".join(parts).strip() or "(no action log this round)"


# =============================================================================
# Budget Hint Messages
# =============================================================================

def _budget_hint(used: int, normal_limit: int) -> str:
    """
    Generate a system hint about remaining tool budget.

    These hints are prepended to tool results so the agent is aware
    of how many calls it has left.

    Args:
        used:             Number of tools used so far.
        normal_limit:     The normal budget limit.

    Returns:
        A hint string to prepend to the tool result.
    """
    remaining = normal_limit - used

    if used >= normal_limit:
        return (
            f"[System: Tool budget exhausted ({used}/{normal_limit}). "
            "Please stop calling tools and let the round end.]"
        )

    if remaining <= 3:
        return (
            f"[System: {used}/{normal_limit} tools used, "
            f"only {remaining} left! Wrap up now.]"
        )

    if remaining <= 8:
        return (
            f"[System: {used}/{normal_limit} tools used, "
            f"{remaining} remaining. Start wrapping up.]"
        )

    return f"[System: {used}/{normal_limit} tools used, {remaining} remaining]"


# =============================================================================
# Stream Processing Helper
# =============================================================================

def _consume_stream(
    response,
    logger=None,
) -> tuple[str, str, dict[int, dict[str, str]]]:
    """
    Consume a streaming LLM response and collect the full message.

    Processes stream chunks to:
    - Broadcast thought text in real-time via logger.thought_chunk()
    - Accumulate reasoning_content for thinking models
    - Reconstruct tool_calls from streaming deltas

    Args:
        response: The streaming response iterator from litellm.completion().
        logger:   Logger instance for real-time broadcasting (optional).

    Returns:
        Tuple of (content, reasoning, tool_calls_map) where:
        - content: Full accumulated text content.
        - reasoning: Full accumulated reasoning_content (or "").
        - tool_calls_map: Dict mapping index -> {id, name, arguments}.
    """
    content = ""
    reasoning = ""
    tool_calls_map = {}  # index -> {"id": str, "name": str, "arguments": str}
    tool_calls_announced = False  # Whether we've notified the frontend
    total_args_chars = 0  # Total chars across all tool call arguments

    for chunk in response:
        if not chunk.choices:
            continue

        choice = chunk.choices[0]
        delta = choice.delta

        # -- Accumulate content and stream to frontend --
        if hasattr(delta, "content") and delta.content:
            content += delta.content
            if logger:
                logger.thought_chunk(delta.content)

        # -- Accumulate reasoning and stream to frontend (DeepSeek Reasoner) --
        reasoning_delta = getattr(delta, "reasoning_content", None)
        if reasoning_delta:
            reasoning += reasoning_delta
            if logger:
                logger.thought_chunk(reasoning_delta)

        # -- Accumulate tool call deltas --
        if hasattr(delta, "tool_calls") and delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index

                # First tool call detected: notify frontend immediately
                # so there's no silence while arguments stream in.
                if not tool_calls_announced:
                    tool_calls_announced = True
                    if logger:
                        logger.loading("[LLM] Preparing tool calls")

                if idx not in tool_calls_map:
                    tool_calls_map[idx] = {"id": "", "name": "", "arguments": ""}
                if tc_delta.id:
                    tool_calls_map[idx]["id"] = tc_delta.id
                if tc_delta.function:
                    if tc_delta.function.name:
                        tool_calls_map[idx]["name"] = tc_delta.function.name
                    if tc_delta.function.arguments:
                        tool_calls_map[idx]["arguments"] += tc_delta.function.arguments
                        total_args_chars += len(tc_delta.function.arguments)

                        # Broadcast real-time progress (no throttle, async send)
                        if logger:
                            name = tool_calls_map[idx]["name"] or "..."
                            logger.loading_update(
                                f"[LLM] Generating {name} ({total_args_chars} chars)"
                            )

        # Check for stream end
        if choice.finish_reason:
            break

    return content, reasoning, tool_calls_map


# =============================================================================
# Main Round Logic
# =============================================================================

def run_round(
    messages: list[dict],
    tool_executor: ToolExecutor,
    model: str,
    api_key: str | None = None,
    normal_limit: int = 20,
    has_skills: bool = True,
    logger=None,
    tool_callback: Callable[[int], None] | None = None,
) -> RoundResult:
    """
    Execute one activation round: LLM <-> tool loop with streaming.

    This function takes the pre-built messages (system + user) and runs
    the tool-calling loop until the LLM stops, the budget is exhausted,
    or an error occurs.

    The LLM is called with stream=True so that:
    - Thought content is broadcast to the dashboard in real-time
    - Tool calls appear before their execution begins
    - Tool results appear immediately after execution completes
    This provides a much better observation experience compared to
    waiting for the entire response before displaying anything.

    Args:
        messages:       Initial messages list [system_msg, ...context_msgs].
        tool_executor:  ToolExecutor instance with safety checks.
        model:          LiteLLM model identifier (e.g. "deepseek/deepseek-chat").
        api_key:        Optional API key override.
        normal_limit:   Normal tool budget per round.
        has_skills:     Whether skills are installed.  When False,
                        skill tools are excluded from the schema.
        logger:         Logger callback object (must have info, loading,
                        tool_call, tool_result, thought_chunk,
                        thought_done methods).
        tool_callback:  Optional callback called after each tool execution
                        with the current tool count: tool_callback(count).

    Returns:
        RoundResult with tools_used, summary, and error.
    """
    total_tool_calls = 0
    hard_limit = normal_limit + 3  # Small buffer so LLM can gracefully stop

    while total_tool_calls < hard_limit:
        # -- Notify dashboard that LLM is being called --
        if logger:
            logger.loading("[LLM] Calling model")

        # -- Call LLM via LiteLLM (streaming) --
        try:
            response = litellm.completion(
                model=model,
                messages=messages,
                tools=get_tools_schema(has_skills),
                tool_choice="auto",
                api_key=api_key,
                stream=True,
            )
        except Exception as e:
            error_msg = f"LLM API error: {type(e).__name__}: {e}"
            if logger:
                logger.info(f"[ERROR] {error_msg}")
            return RoundResult(
                tools_used=total_tool_calls,
                summary=_extract_summary(messages),
                action_log=_extract_action_log(messages),
                error=error_msg,
            )

        # -- Process the stream --
        try:
            content, reasoning, tool_calls_map = _consume_stream(response, logger)
        except Exception as e:
            error_msg = f"Stream error: {type(e).__name__}: {e}"
            if logger:
                logger.info(f"[ERROR] {error_msg}")
            return RoundResult(
                tools_used=total_tool_calls,
                summary=_extract_summary(messages),
                action_log=_extract_action_log(messages),
                error=error_msg,
            )

        # -- Finalize thought display --
        # For thinking models: reasoning_content is the "thought", content is the final answer
        if reasoning and logger:
            logger.thought_done(reasoning)
        if content and logger:
            logger.thought_done(content)

        # Timestamp for this LLM turn (used by _extract_summary)
        turn_ts = datetime.now().strftime("%H:%M:%S")

        # -- No tool calls: round ends naturally --
        if not tool_calls_map:
            assistant_msg = {"role": "assistant", "content": content or "", "_timestamp": turn_ts}
            if reasoning:
                assistant_msg["reasoning_content"] = reasoning
            messages.append(assistant_msg)
            break

        # -- Build assistant message with tool calls --
        assistant_msg = {"role": "assistant", "content": content or "", "_timestamp": turn_ts}
        if reasoning:
            assistant_msg["reasoning_content"] = reasoning

        tool_calls_list = []
        for idx in sorted(tool_calls_map.keys()):
            tc = tool_calls_map[idx]
            tool_calls_list.append({
                "id": tc["id"],
                "type": "function",
                "function": {
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                },
            })

        assistant_msg["tool_calls"] = tool_calls_list
        messages.append(assistant_msg)

        # -- Execute each tool call (one by one, with sync broadcasts) --
        for tc_data in tool_calls_list:
            func_name = tc_data["function"]["name"]
            call_id = tc_data["id"]

            # Parse arguments (with JSON repair fallback)
            raw_args = tc_data["function"]["arguments"]
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                # LLM produced invalid JSON — attempt repair
                repaired = _repair_json(raw_args)
                if repaired is not None:
                    args = repaired
                    if logger:
                        logger.info(f"[JSON-REPAIR] Repaired arguments for {func_name}")
                else:
                    args = {}
                    if logger:
                        logger.tool_call(func_name, {"_raw": raw_args[:200]})
                    result = (
                        "(error: failed to parse tool arguments as JSON. "
                        "Tip: for large files, try writing smaller sections "
                        "or use shell_execute with 'cat << EOF > file')"
                    )
                    total_tool_calls += 1
                    if tool_callback:
                        tool_callback(total_tool_calls)
                    hint = _budget_hint(total_tool_calls, normal_limit)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": f"{hint}\n\n{result}",
                    })
                    if logger:
                        logger.tool_result(result)
                    continue

            if logger:
                logger.tool_call(func_name, args)

            # -- Budget enforcement --
            if total_tool_calls >= normal_limit:
                result = (
                    f"[System: Tool budget exhausted ({total_tool_calls}/{normal_limit}). "
                    "Please stop calling tools and let the round end.]"
                )
                total_tool_calls += 1
                if tool_callback:
                    tool_callback(total_tool_calls)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": result,
                })
                if logger:
                    logger.tool_result(result)
                continue

            # -- Execute the tool (with loading indicator) --
            if logger:
                logger.loading(f"[TOOL] Executing {func_name}")
            result = tool_executor.execute(func_name, args)
            total_tool_calls += 1
            if tool_callback:
                tool_callback(total_tool_calls)

            # Prepend budget hint
            hint = _budget_hint(total_tool_calls, normal_limit)
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": f"{hint}\n\n{result}",
            })

            if logger:
                logger.tool_result(result)

    # -- Round complete --
    if total_tool_calls >= hard_limit and logger:
        logger.info(f"[LIMIT] Reached hard limit ({hard_limit}) for this round")

    return RoundResult(
        tools_used=total_tool_calls,
        summary=_extract_summary(messages),
        action_log=_extract_action_log(messages),
    )
