"""
Awakener - Agent Core
LLM calls via LiteLLM, context assembly, tool dispatch loop.
"""

import json
import os
from datetime import datetime

import litellm
from tools import TOOLS_SCHEMA, execute_tool


# ── Persona Loading ───────────────────────────────────────────────────────

def load_persona(project_dir: str) -> str:
    """Load persona from persona.md alongside the project root."""
    persona_path = os.path.join(project_dir, "persona.md")
    try:
        with open(persona_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "你是一个自主运行的AI Agent，拥有一台Linux服务器。"


# ── Notebook Loading ──────────────────────────────────────────────────────

def load_notebook(config: dict) -> str:
    """Load the agent's notebook. Returns content or empty message."""
    notebook_path = os.path.join(
        config["agent_home"],
        config.get("notebook_file", "notebook.md")
    )
    try:
        with open(notebook_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        return content if content else "(空白笔记本)"
    except FileNotFoundError:
        return "(空白笔记本)"


# ── Context Assembly ──────────────────────────────────────────────────────

def build_system_message(persona: str) -> str:
    """Build the system message: persona + tool hints + notebook rules."""
    return f"""{persona}

---

你有以下工具可以使用：
- shell_execute(command) — 执行Shell命令，返回stdout和stderr
- read_file(path) — 读取文件内容
- write_file(path, content, append?) — 写入文件，append=true时追加

你的笔记本路径：{{notebook_path}}
它的内容每次醒来会自动呈现给你。
你可以用 write_file 随时更新它。
如果你失去记忆，笔记本是你唯一的线索。"""


def build_user_message(
    step: int,
    notebook_content: str,
    recent_memories: list[dict],
    notebook_path: str,
) -> str:
    """Build the user message: time + notebook + recent memories."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    parts = []

    parts.append(f"当前时间：{now}")
    parts.append(f"第 {step} 轮激活")
    parts.append("")

    # Notebook
    parts.append("## 你的笔记本")
    parts.append(notebook_content)
    parts.append("")

    # Recent memories (rolling window of past rounds' outputs)
    if recent_memories:
        parts.append("## 近期记忆片段")
        for mem in recent_memories:
            parts.append(f"--- 第 {mem['step']} 轮 | {mem['time']} ---")
            parts.append(mem["content"])
            parts.append("")

    parts.append("你醒来了。")

    # Replace notebook path placeholder in system prompt won't work here,
    # but we include it in the user message context for clarity
    return "\n".join(parts)


# ── Extract Round Summary ─────────────────────────────────────────────────

def extract_round_summary(messages: list[dict], max_chars: int = 500) -> str:
    """
    Extract complete agent context from this round (reasoning + content).
    
    This creates a continuous context window similar to normal chat history.
    Includes all reasoning_content and content from assistant messages,
    but excludes tool calls and tool results.
    """
    parts = []

    for msg in messages:
        if msg.get("role") == "assistant":
            # Include reasoning (thinking process)
            if msg.get("reasoning_content"):
                parts.append(f"[思考] {msg['reasoning_content']}")
            
            # Include formal output
            if msg.get("content"):
                parts.append(f"[输出] {msg['content']}")

    full_text = "\n\n".join(parts).strip()

    if not full_text:
        full_text = "(本轮无文字输出)"

    # Truncate if too long, but try to keep last part
    if len(full_text) > max_chars:
        full_text = "..." + full_text[-(max_chars-3):]

    return full_text


# ── Main Activation Logic ─────────────────────────────────────────────────

def run_activation(
    config: dict,
    project_dir: str,
    step: int,
    recent_memories: list[dict],
    logger,
) -> tuple[int, str]:
    """
    Run one activation round.

    Args:
        config: Configuration dict
        project_dir: Path to the awakener project root
        step: Current activation step number
        recent_memories: List of recent round summaries
        logger: Logger instance

    Returns:
        (tool_call_count, round_summary) tuple
    """
    # Load persona and notebook
    persona = load_persona(project_dir)
    notebook_content = load_notebook(config)
    notebook_path = os.path.join(
        config["agent_home"],
        config.get("notebook_file", "notebook.md")
    )

    # Build messages
    system_msg = build_system_message(persona).replace(
        "{notebook_path}", notebook_path
    )
    user_msg = build_user_message(
        step=step,
        notebook_content=notebook_content,
        recent_memories=recent_memories,
        notebook_path=notebook_path,
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    logger.info(f"[CONTEXT] Notebook: {len(notebook_content)} chars | "
                f"Recent memories: {len(recent_memories)} rounds")

    # ── Tool calling loop ──
    total_tool_calls = 0
    normal_limit = config.get("max_tool_calls_per_activation", 20)
    hard_limit = normal_limit + 10  # Extra 10 calls for forced notebook writing
    
    notebook_path = os.path.join(config["agent_home"], config.get("notebook_file", "notebook.md"))

    while total_tool_calls < hard_limit:
        # Call LLM via LiteLLM
        try:
            response = litellm.completion(
                model=config["model"],
                messages=messages,
                tools=TOOLS_SCHEMA,
                tool_choice="auto",
                api_key=config.get("api_key"),
            )
        except Exception as e:
            logger.error(f"LLM API call failed: {e}")
            break

        message = response.choices[0].message

        # Log reasoning (for thinking models)
        reasoning = getattr(message, "reasoning_content", None)
        if reasoning:
            logger.info(f"[REASONING] {reasoning[:500]}{'...' if len(reasoning) > 500 else ''}")

        # Log agent's output
        if message.content:
            logger.thought(message.content)

        # If no tool calls, round is complete
        if not message.tool_calls:
            final_msg = {"role": "assistant", "content": message.content or ""}
            if reasoning:
                final_msg["reasoning_content"] = reasoning
            messages.append(final_msg)
            break

        # Build assistant message for conversation history
        # DeepSeek reasoner requires reasoning_content in assistant messages
        assistant_msg = {"role": "assistant", "content": message.content or ""}
        if reasoning:
            assistant_msg["reasoning_content"] = reasoning
        if message.tool_calls:
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

        # Execute each tool call
        for tool_call in message.tool_calls:
            func_name = tool_call.function.name

            # Parse arguments
            try:
                args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                logger.tool_call(func_name, {"_raw": tool_call.function.arguments})
                result = "(error: failed to parse arguments as JSON)"
                total_tool_calls += 1
                
                if total_tool_calls >= normal_limit:
                    system_prefix = f"[System: ⚠️ 已到达工具使用上限。解析错误也计入次数。\n请使用 write_file 更新笔记本后停止。]\n\n"
                else:
                    remaining = normal_limit - total_tool_calls
                    if remaining <= 3:
                        system_prefix = f"[System: ⚠️ 本轮已用 {total_tool_calls} 次工具，仅剩 {remaining} 次！请尽快完成本轮任务并更新笔记本]\n\n"
                    elif remaining <= 8:
                        system_prefix = f"[System: 本轮已用 {total_tool_calls} 次工具，剩余 {remaining} 次。建议开始收尾]\n\n"
                    else:
                        system_prefix = f"[System: 本轮已用 {total_tool_calls} 次工具，剩余 {remaining} 次]\n\n"
                
                result_with_hint = system_prefix + result
                logger.tool_result(result)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result_with_hint,
                })
                continue

            logger.tool_call(func_name, args)

            # Check if we've exceeded normal limit
            if total_tool_calls >= normal_limit:
                # Force mode: only allow write_file to notebook
                if func_name != "write_file":
                    result = f"[System: ⚠️ 已到达工具使用上限 ({normal_limit}/{normal_limit})。\n现在只能使用 write_file 更新笔记本。\n请立即保存本轮记忆到 {notebook_path}，然后停止调用工具进入休眠。]"
                    total_tool_calls += 1
                    logger.tool_result(result)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                    continue
                
                # Check if writing to notebook
                target_path = os.path.abspath(args.get("path", ""))
                expected_path = os.path.abspath(notebook_path)
                if target_path != expected_path:
                    result = f"[System: ⚠️ 已到达工具使用上限。\n请使用 write_file 更新笔记本 ({notebook_path})，\n而不是其他文件 ({target_path})。]"
                    total_tool_calls += 1
                    logger.tool_result(result)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result,
                    })
                    continue

            # Execute tool
            result = execute_tool(func_name, args, config)
            total_tool_calls += 1
            
            # Prepend system info: remaining tool calls
            if total_tool_calls >= normal_limit:
                system_prefix = f"[System: 笔记本已更新。本轮共使用 {total_tool_calls} 次工具。\n请停止调用工具，让本轮激活正常结束。]\n\n"
            else:
                remaining = normal_limit - total_tool_calls
                if remaining <= 3:
                    system_prefix = f"[System: ⚠️ 本轮已用 {total_tool_calls} 次工具，仅剩 {remaining} 次！请尽快完成本轮任务并更新笔记本]\n\n"
                elif remaining <= 8:
                    system_prefix = f"[System: 本轮已用 {total_tool_calls} 次工具，剩余 {remaining} 次。建议开始收尾]\n\n"
                else:
                    system_prefix = f"[System: 本轮已用 {total_tool_calls} 次工具，剩余 {remaining} 次]\n\n"
            
            result_with_hint = system_prefix + result
            
            logger.tool_result(result)

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result_with_hint,
            })


    if total_tool_calls >= hard_limit:
        logger.info(f"[LIMIT] Reached hard limit ({hard_limit})")

    # Extract this round's summary for the rolling memory window
    max_chars = config.get("context_window", {}).get("max_chars_per_round", 500)
    round_summary = extract_round_summary(messages, max_chars)

    return total_tool_calls, round_summary
