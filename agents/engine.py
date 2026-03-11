"""
Awakener - Agent Engine (Single Round)
=========================================
Runs one activation round: calls the LLM via LiteLLM, dispatches tool
calls, and enforces the tool budget.

The round lifecycle:
    1. Build system + user messages (done by caller)
    2. Enter the tool-calling loop (streaming)
    3. LLM streams response -> broadcast thoughts in real-time
    4. Collect tool_calls from stream -> execute one by one
    5. Repeat until LLM stops calling tools or budget exhausted
    6. Extract round summary for timeline
"""

import json
from datetime import datetime
from typing import Callable

import litellm

from agents.tools import get_tools_schema
from agents.tools.executor import ToolExecutor
from core.llm import repair_json


# =============================================================================
# Round Result
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
    return full_text or "(no text output this round)"


def _extract_action_log(messages: list[dict]) -> str:
    parts = []
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
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
# Budget Hints
# =============================================================================

def _budget_hint(used: int, normal_limit: int) -> str:
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
# Stream Processing
# =============================================================================

def _consume_stream(
    response,
    logger=None,
) -> tuple[str, str, dict[int, dict[str, str]]]:
    content = ""
    reasoning = ""
    tool_calls_map: dict[int, dict[str, str]] = {}
    tool_calls_announced = False
    total_args_chars = 0

    for chunk in response:
        if not chunk.choices:
            continue
        choice = chunk.choices[0]
        delta = choice.delta

        if hasattr(delta, "content") and delta.content:
            content += delta.content
            if logger:
                logger.thought_chunk(delta.content)

        reasoning_delta = getattr(delta, "reasoning_content", None)
        if reasoning_delta:
            reasoning += reasoning_delta
            if logger:
                logger.thought_chunk(reasoning_delta)

        if hasattr(delta, "tool_calls") and delta.tool_calls:
            for tc_delta in delta.tool_calls:
                idx = tc_delta.index
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
                        if logger:
                            name = tool_calls_map[idx]["name"] or "..."
                            logger.loading_update(
                                f"[LLM] Generating {name} ({total_args_chars} chars)"
                            )

        if choice.finish_reason:
            break

    return content, reasoning, tool_calls_map


# =============================================================================
# Reasoning Content Consistency
# =============================================================================

def _ensure_reasoning_content(messages: list[dict]) -> None:
    has_any_reasoning = any(
        msg.get("role") == "assistant" and "reasoning_content" in msg
        for msg in messages
    )
    if not has_any_reasoning:
        return
    for msg in messages:
        if msg.get("role") == "assistant" and "reasoning_content" not in msg:
            msg["reasoning_content"] = ""


# =============================================================================
# Main Round Logic
# =============================================================================

def run_round(
    messages: list[dict],
    tool_executor: ToolExecutor,
    model: str,
    api_key: str | None = None,
    api_base: str = "",
    normal_limit: int = 20,
    logger=None,
    tool_callback: Callable[[int], None] | None = None,
) -> RoundResult:
    """
    Execute one activation round: LLM <-> tool loop with streaming.
    """
    total_tool_calls = 0
    hard_limit = normal_limit + 3

    while total_tool_calls < hard_limit:
        if logger:
            logger.loading("[LLM] Calling model")

        _ensure_reasoning_content(messages)

        try:
            kwargs = dict(
                model=model,
                messages=messages,
                tools=get_tools_schema(),
                tool_choice="auto",
                api_key=api_key,
                stream=True,
            )
            if api_base:
                kwargs["api_base"] = api_base
            response = litellm.completion(**kwargs)
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

        if reasoning and logger:
            logger.thought_done(reasoning)
        if content and logger:
            logger.thought_done(content)

        turn_ts = datetime.now().strftime("%H:%M:%S")

        if not tool_calls_map:
            assistant_msg = {"role": "assistant", "content": content or "", "_timestamp": turn_ts}
            if reasoning:
                assistant_msg["reasoning_content"] = reasoning
            messages.append(assistant_msg)
            break

        assistant_msg = {"role": "assistant", "content": content or "", "_timestamp": turn_ts}
        if reasoning:
            assistant_msg["reasoning_content"] = reasoning

        tool_calls_list = []
        for idx in sorted(tool_calls_map.keys()):
            tc = tool_calls_map[idx]
            tool_calls_list.append({
                "id": tc["id"],
                "type": "function",
                "function": {"name": tc["name"], "arguments": tc["arguments"]},
            })

        assistant_msg["tool_calls"] = tool_calls_list
        messages.append(assistant_msg)

        for tc_data in tool_calls_list:
            func_name = tc_data["function"]["name"]
            call_id = tc_data["id"]
            raw_args = tc_data["function"]["arguments"]

            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                repaired = repair_json(raw_args)
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

            if logger:
                logger.loading(f"[TOOL] Executing {func_name}")
            result = tool_executor.execute(func_name, args)
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

    if total_tool_calls >= hard_limit and logger:
        logger.info(f"[LIMIT] Reached hard limit ({hard_limit}) for this round")

    return RoundResult(
        tools_used=total_tool_calls,
        summary=_extract_summary(messages),
        action_log=_extract_action_log(messages),
    )
