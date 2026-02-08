"""
Awakener - Agent Core (Single Round)
=======================================
Runs one activation round: calls the LLM via LiteLLM, dispatches tool
calls, enforces the tool budget, and ensures the agent writes a notebook
entry before the round ends.

The round lifecycle:
    1. Build system + user messages (done by caller)
    2. Enter the tool-calling loop
    3. LLM returns tool_calls -> execute them -> feed results back
    4. Repeat until LLM stops calling tools or budget exhausted
    5. Extract round summary for timeline

Budget enforcement:
    - normal_limit: Max tool calls the agent can use freely
    - After normal_limit: only notebook_write is allowed
    - hard_limit (normal + 5): force stop even without notebook

DeepSeek reasoner support:
    - reasoning_content from the response is preserved in the
      conversation history so the model doesn't lose its thinking chain.
"""

import json
import litellm
from activator.tools import ToolExecutor, TOOLS_SCHEMA


# =============================================================================
# Round Result Data Class
# =============================================================================

class RoundResult:
    """
    Holds the outcome of a single activation round.

    Attributes:
        tools_used:     Total tool calls made this round.
        notebook_saved: Whether the agent called notebook_write.
        summary:        Text summary extracted from the agent's messages.
        error:          Error message if the round failed, else None.
    """

    def __init__(
        self,
        tools_used: int = 0,
        notebook_saved: bool = False,
        summary: str = "",
        error: str | None = None,
    ):
        self.tools_used = tools_used
        self.notebook_saved = notebook_saved
        self.summary = summary
        self.error = error


# =============================================================================
# Summary Extraction
# =============================================================================

def _extract_summary(messages: list[dict], max_chars: int = 500) -> str:
    """
    Extract a brief summary from the agent's messages this round.

    Collects reasoning_content and content from assistant messages,
    skipping tool calls and tool results for brevity.

    Args:
        messages:  Full conversation history for this round.
        max_chars: Maximum characters for the summary.

    Returns:
        A text summary of the agent's thoughts and outputs.
    """
    parts = []
    for msg in messages:
        if msg.get("role") == "assistant":
            if msg.get("reasoning_content"):
                parts.append(f"[Thinking] {msg['reasoning_content']}")
            if msg.get("content"):
                parts.append(msg["content"])

    full_text = "\n".join(parts).strip()
    if not full_text:
        full_text = "(no text output this round)"

    if len(full_text) > max_chars:
        full_text = full_text[:max_chars] + "..."

    return full_text


# =============================================================================
# Budget Hint Messages
# =============================================================================

def _budget_hint(used: int, normal_limit: int, notebook_written: bool) -> str:
    """
    Generate a system hint about remaining tool budget.

    These hints are prepended to tool results so the agent is aware
    of how many calls it has left and whether it should save its notebook.

    Args:
        used:             Number of tools used so far.
        normal_limit:     The normal budget limit.
        notebook_written: Whether notebook_write has been called.

    Returns:
        A hint string to prepend to the tool result.
    """
    remaining = normal_limit - used

    if used >= normal_limit:
        if notebook_written:
            return (
                f"[System: Tool budget exhausted ({used}/{normal_limit}). "
                "Notebook saved. Please stop calling tools and let the round end.]"
            )
        else:
            return (
                f"[System: Tool budget exhausted ({used}/{normal_limit}). "
                "Only notebook_write is allowed now. "
                "Save your notes immediately!]"
            )

    if remaining <= 3:
        save_hint = "" if notebook_written else " Remember to save your notebook!"
        return (
            f"[System: {used}/{normal_limit} tools used, "
            f"only {remaining} left!{save_hint}]"
        )

    if remaining <= 8:
        save_hint = "" if notebook_written else " Start wrapping up and save your notebook."
        return (
            f"[System: {used}/{normal_limit} tools used, "
            f"{remaining} remaining.{save_hint}]"
        )

    return f"[System: {used}/{normal_limit} tools used, {remaining} remaining]"


# =============================================================================
# Main Round Logic
# =============================================================================

def run_round(
    messages: list[dict],
    tool_executor: ToolExecutor,
    model: str,
    api_key: str | None = None,
    normal_limit: int = 20,
    logger=None,
) -> RoundResult:
    """
    Execute one activation round: LLM <-> tool loop.

    This function takes the pre-built messages (system + user) and runs
    the tool-calling loop until the LLM stops, the budget is exhausted,
    or an error occurs.

    Args:
        messages:       Initial messages list [system_msg, user_msg].
        tool_executor:  ToolExecutor instance with safety checks.
        model:          LiteLLM model identifier (e.g. "deepseek/deepseek-chat").
        api_key:        Optional API key override.
        normal_limit:   Normal tool budget per round.
        logger:         Logger callback object (must have info, tool_call,
                        tool_result, thought methods).

    Returns:
        RoundResult with tools_used, notebook_saved, summary, and error.
    """
    total_tool_calls = 0
    hard_limit = normal_limit + 5  # Extra buffer for forced notebook write

    while total_tool_calls < hard_limit:
        # -- Call LLM via LiteLLM --
        try:
            response = litellm.completion(
                model=model,
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                api_key=api_key,
            )
        except Exception as e:
            error_msg = f"LLM API error: {type(e).__name__}: {e}"
            if logger:
                logger.info(f"[ERROR] {error_msg}")
            return RoundResult(
                tools_used=total_tool_calls,
                notebook_saved=tool_executor.notebook_written,
                summary=_extract_summary(messages),
                error=error_msg,
            )

        message = response.choices[0].message
        reasoning = getattr(message, "reasoning_content", None)

        # Log reasoning (for thinking models like DeepSeek Reasoner)
        if reasoning and logger:
            preview = reasoning[:500] + ("..." if len(reasoning) > 500 else "")
            logger.info(f"[REASONING] {preview}")

        # Log the agent's text output
        if message.content and logger:
            logger.thought(message.content)

        # -- No tool calls: round ends naturally --
        if not message.tool_calls:
            assistant_msg = {"role": "assistant", "content": message.content or ""}
            if reasoning:
                assistant_msg["reasoning_content"] = reasoning
            messages.append(assistant_msg)
            break

        # -- Build assistant message with tool calls --
        assistant_msg = {"role": "assistant", "content": message.content or ""}
        if reasoning:
            assistant_msg["reasoning_content"] = reasoning
        assistant_msg["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in message.tool_calls
        ]
        messages.append(assistant_msg)

        # -- Execute each tool call --
        for tool_call in message.tool_calls:
            func_name = tool_call.function.name
            call_id = tool_call.id

            # Parse arguments
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                args = {}
                if logger:
                    logger.tool_call(func_name, {"_raw": tool_call.function.arguments})
                result = "(error: failed to parse tool arguments as JSON)"
                total_tool_calls += 1
                hint = _budget_hint(total_tool_calls, normal_limit, tool_executor.notebook_written)
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
                # Over budget: only notebook_write allowed
                if func_name != "notebook_write":
                    if tool_executor.notebook_written:
                        result = (
                            f"[System: Tool budget exhausted ({total_tool_calls}/{normal_limit}). "
                            "Notebook already saved. Please stop calling tools.]"
                        )
                    else:
                        result = (
                            f"[System: Tool budget exhausted ({total_tool_calls}/{normal_limit}). "
                            "You must call notebook_write now to save your progress.]"
                        )
                    total_tool_calls += 1
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": result,
                    })
                    if logger:
                        logger.tool_result(result)
                    continue

            # -- Execute the tool --
            result = tool_executor.execute(func_name, args)
            total_tool_calls += 1

            # Prepend budget hint
            hint = _budget_hint(total_tool_calls, normal_limit, tool_executor.notebook_written)
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
        notebook_saved=tool_executor.notebook_written,
        summary=_extract_summary(messages),
    )
