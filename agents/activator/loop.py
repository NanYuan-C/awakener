"""
Awakener - Activation Loop
==============================
The main entry point for the agent activation engine.

This module runs in a background thread (launched by api/manager.py)
and orchestrates the activation cycle:

    1. Load config, resolve paths
    2. Initialize MemoryManager and resume round counter
    3. Enter the loop:
       a. Build context (system + user messages)
       b. Create ToolExecutor for this round
       c. Run one activation round (engine.py)
       d. Record results (timeline, logs)
       e. Broadcast status via WebSocket
       f. Wait for the configured interval (or stop_event)
    4. Exit cleanly when stop_event is set
"""

import os
import time
import gc
import asyncio
import threading
from datetime import datetime, timezone
from typing import Any, Callable

# Importing tool modules triggers their registration with the tool registry
import agents.tools.shell  # noqa: F401
import agents.tools.file   # noqa: F401

from services.memory import MemoryManager
from agents.tools.executor import ToolExecutor
from agents.tools.shell import detect_host_env
from agents.activator.context import build_system_message, build_context_messages
from agents.engine import run_round
from agents.auditor.snapshot import update_snapshot, SnapshotUpdateError
from core.config import DEFAULTS
from core.llm import resolve_api_key
from core.logger import ActivatorLogger


def run_activation_loop(
    config: dict,
    ws_manager: Any = None,
    stop_event: threading.Event | None = None,
    state_callback: Callable[[dict], None] | None = None,
    project_dir: str = "",
    event_loop: asyncio.AbstractEventLoop | None = None,
) -> None:
    """
    Main activation loop. Runs in a background thread.

    This function blocks until stop_event is set or an unrecoverable
    error occurs. It manages the full lifecycle of activation rounds.
    """
    if stop_event is None:
        stop_event = threading.Event()

    # -- Resolve configuration --
    agent_config = config.get("agent", {})
    agent_home = agent_config.get("home", "/home/agent")
    model = agent_config.get("model", "deepseek/deepseek-chat")
    api_base = agent_config.get("api_base", "") or ""
    interval = agent_config.get("interval", 60)
    max_tool_calls = agent_config.get("max_tool_calls", 20)
    shell_timeout = agent_config.get("shell_timeout", 30)
    max_output = agent_config.get("max_output_chars", 4000)
    history_rounds = agent_config.get("history_rounds", 3)
    persona = "persona"
    snapshot_model = agent_config.get("snapshot_model", "") or ""

    if snapshot_model and "/" not in snapshot_model:
        provider_prefix = model.split("/")[0] if "/" in model else ""
        if provider_prefix:
            snapshot_model = f"{provider_prefix}/{snapshot_model}"

    api_key = resolve_api_key(model)

    # -- Initialize subsystems --
    data_dir = os.path.join(project_dir, "data")
    log_dir = os.path.join(data_dir, "logs")
    skills_dir = os.path.join(agent_home, "skills")

    memory = MemoryManager(data_dir)
    logger = ActivatorLogger(log_dir, ws_manager, event_loop)

    os.makedirs(skills_dir, exist_ok=True)
    os.makedirs(agent_home, exist_ok=True)

    round_num = memory.get_last_round_number() + 1
    activator_pid = os.getpid()

    host_env = detect_host_env()
    web_config = config.get("web", {})
    host_env["server_port"] = web_config.get("port", DEFAULTS["web"]["port"])

    logger.info(f"[START] Activator started | Model: {model} | Home: {agent_home}")
    if host_env:
        parts = [f"{k}={v}" for k, v in host_env.items()]
        logger.info(f"[START] Host env: {', '.join(parts)}")
    logger.info(f"[START] Interval: {interval}s | Tool budget: {max_tool_calls} | Resume at round {round_num}")

    if state_callback:
        state_callback({"state": "running", "round": round_num})

    # -- Main loop --
    while not stop_event.is_set():
        round_start_time = time.time()
        round_start_iso = datetime.now(timezone.utc).isoformat()
        logger.round_start(round_num)

        # Reload agent settings each round
        try:
            from core.config import ConfigManager
            _live_cfg = ConfigManager(project_dir).load().get("agent", {})
            max_tool_calls = _live_cfg.get("max_tool_calls", max_tool_calls)
            shell_timeout = _live_cfg.get("shell_timeout", shell_timeout)
            max_output = _live_cfg.get("max_output_chars", max_output)
            interval = _live_cfg.get("interval", interval)
            history_rounds = _live_cfg.get("history_rounds", history_rounds)
            snapshot_model = _live_cfg.get("snapshot_model", "") or ""
            if snapshot_model and "/" not in snapshot_model:
                provider_prefix = model.split("/")[0] if "/" in model else ""
                if provider_prefix:
                    snapshot_model = f"{provider_prefix}/{snapshot_model}"
            api_base = _live_cfg.get("api_base", "") or ""
        except Exception:
            pass

        if state_callback:
            state_callback({
                "state": "running",
                "round": round_num,
                "round_start_time": round_start_iso,
                "round_tools_used": 0,
            })

        if ws_manager and event_loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    ws_manager.broadcast({
                        "type": "round",
                        "round": round_num,
                        "round_start_time": round_start_iso,
                        "round_tools_used": 0,
                    }),
                    event_loop,
                )
            except Exception:
                pass

        system_msg = build_system_message(
            project_dir, persona, skills_dir, data_dir,
            agent_home=agent_home,
        )

        context_msgs = build_context_messages(
            round_num, max_tool_calls, memory,
            agent_home=agent_home,
            data_dir=data_dir,
            history_rounds=history_rounds,
        )

        messages = [
            {"role": "system", "content": system_msg},
            *context_msgs,
        ]

        logger.info(
            f"[CONTEXT] Persona: {persona} | "
            f"Timeline: {len(memory.get_recent_timeline(count=1))}"
        )

        tool_exec = ToolExecutor(
            agent_home=agent_home,
            project_dir=project_dir,
            activator_pid=activator_pid,
            timeout=shell_timeout,
            max_output=max_output,
            host_env=host_env,
        )

        def on_tool_used(count: int):
            if state_callback:
                state_callback({"round_tools_used": count})
            if ws_manager and event_loop:
                try:
                    asyncio.run_coroutine_threadsafe(
                        ws_manager.broadcast({
                            "type": "tools",
                            "round": round_num,
                            "round_tools_used": count,
                        }),
                        event_loop,
                    )
                except Exception:
                    pass

        result = run_round(
            messages=messages,
            tool_executor=tool_exec,
            model=model,
            api_key=api_key,
            api_base=api_base,
            normal_limit=max_tool_calls,
            logger=logger,
            tool_callback=on_tool_used,
        )

        duration = time.time() - round_start_time

        timeline_entry = {
            "round": round_num,
            "tools_used": result.tools_used,
            "duration": round(duration, 1),
            "summary": result.summary,
            "action_log": result.action_log,
        }
        memory.append_timeline(
            round_num=round_num,
            tools_used=result.tools_used,
            duration=duration,
            summary=result.summary,
            action_log=result.action_log,
        )

        logger.round_end(round_num, result.tools_used, duration)

        if state_callback:
            state_callback({
                "state": "waiting",
                "round": round_num,
                "tools": result.tools_used,
                "summary": result.summary[:200],
            })

        try:
            update_snapshot(
                data_dir=data_dir,
                timeline_entry=timeline_entry,
                round_num=round_num,
                snapshot_model=snapshot_model if snapshot_model else None,
                main_model=model,
                api_key=api_key,
                api_base=api_base,
                logger=logger,
            )
        except SnapshotUpdateError as e:
            error_msg = (
                f"[SNAPSHOT] CRITICAL — snapshot update failed on all models: {e}. "
                "Stopping activation loop."
            )
            logger.info(error_msg)
            if state_callback:
                state_callback({
                    "state": "error",
                    "round": round_num,
                    "error": error_msg,
                })
            break

        round_num += 1

        del messages, system_msg, context_msgs, tool_exec, result, timeline_entry
        gc.collect()

        if interval > 0 and not stop_event.is_set():
            logger.waiting(interval)
            stop_event.wait(timeout=interval)
        elif stop_event.is_set():
            break

    logger.info("[STOP] Activator stopped gracefully")
    if state_callback:
        state_callback({"state": "idle", "round": round_num - 1})
