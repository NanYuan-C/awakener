"""
Awakener - Activation Loop
==============================
The main entry point for the agent activation engine.

This module runs in a background thread (launched by server/manager.py)
and orchestrates the activation cycle:

    1. Load config, resolve paths
    2. Initialize MemoryManager and resume round counter
    3. Enter the loop:
       a. Build context (system + user messages)
       b. Create ToolExecutor for this round
       c. Run one activation round (agent.py)
       d. Record results (timeline, logs)
       e. Broadcast status via WebSocket
       f. Wait for the configured interval (or stop_event)
    4. Exit cleanly when stop_event is set

Logging:
    Run logs are stored in per-day files: data/logs/YYYY-MM-DD.log
    Each round is separated by a clear header.
    Log entries are also broadcast via WebSocket to the dashboard.
"""

import os
import time
import asyncio
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from activator.memory import MemoryManager
from activator.tools import ToolExecutor
from activator.context import build_system_message, build_user_message
from activator.agent import run_round


# =============================================================================
# Activator Logger
# =============================================================================

class ActivatorLogger:
    """
    Dual-output logger: writes to per-day log files AND broadcasts
    via WebSocket to the web dashboard.

    Log files are stored in data/logs/ with filenames like 2026-02-09.log.
    Each round starts with a clear separator header.

    Attributes:
        log_dir:    Directory for log files (data/logs/).
        ws_manager: WebSocket manager for broadcasting (may be None).
        _loop:      asyncio event loop for WS broadcasts (may be None).
    """

    def __init__(self, log_dir: str, ws_manager: Any = None, event_loop: asyncio.AbstractEventLoop | None = None):
        """
        Initialize the logger.

        Args:
            log_dir:    Directory path for log files.
            ws_manager: WebSocket manager instance (optional).
            event_loop: The main asyncio event loop (for thread-safe WS broadcast).
        """
        self.log_dir = log_dir
        self.ws_manager = ws_manager
        self._loop = event_loop

        os.makedirs(log_dir, exist_ok=True)

    def _get_log_path(self) -> str:
        """Get today's log file path."""
        today = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"{today}.log")

    def _timestamp(self) -> str:
        """Get current time formatted for log entries."""
        return datetime.now().strftime("%H:%M:%S")

    def _write(self, text: str) -> None:
        """Append a line to today's log file."""
        try:
            with open(self._get_log_path(), "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass

    def _broadcast(self, msg_type: str, data: dict, wait: bool = True) -> None:
        """
        Broadcast a message via WebSocket from the activator thread.

        By default, this method waits for the broadcast to complete before
        returning. This ensures messages arrive at the frontend in order
        and with visible time separation (so they don't all appear at once).

        Args:
            msg_type: Message type string (e.g. "log", "tool_call").
            data:     Message data dictionary.
            wait:     If True (default), block until the broadcast is sent.
                      Set to False for high-frequency streaming data.
        """
        if not self.ws_manager or not self._loop:
            return

        message = {"type": msg_type, "data": data}
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.ws_manager.broadcast(message),
                self._loop,
            )
            if wait:
                # Block until the WebSocket send completes, so the next
                # message is only queued after this one is delivered.
                future.result(timeout=5)
        except Exception:
            pass

    def round_start(self, round_num: int) -> None:
        """
        Log the start of a new round with a separator header.

        Broadcasts both a status update ("running") and a round event.
        The status broadcast ensures the frontend badge/buttons update
        correctly when transitioning from "waiting" to "running".

        Args:
            round_num: The round number starting.
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        separator = "=" * 50
        header = (
            f"\n{separator}\n"
            f"Round {round_num} | {now}\n"
            f"{separator}"
        )
        self._write(header)
        print(header, flush=True)
        self._broadcast("status", {"status": "running", "round": round_num})
        self._broadcast("round", {"step": round_num, "event": "started"})

    def round_end(self, round_num: int, tools_used: int, duration: float, notebook_saved: bool) -> None:
        """
        Log the end of a round.

        Args:
            round_num:      Completed round number.
            tools_used:     Number of tool calls made.
            duration:       Round duration in seconds.
            notebook_saved: Whether the agent saved a notebook entry.
        """
        ts = self._timestamp()
        note_status = "saved" if notebook_saved else "NOT SAVED"
        text = (
            f"[{ts}] [DONE] Round {round_num} complete | "
            f"Tools: {tools_used} | Time: {duration:.1f}s | "
            f"Notebook: {note_status}"
        )
        self._write(text)
        print(text, flush=True)
        self._broadcast("round", {
            "step": round_num,
            "event": "completed",
            "tools_used": tools_used,
            "duration": round(duration, 1),
            "notebook_saved": notebook_saved,
        })

    def info(self, text: str) -> None:
        """Log an informational message. Also prints to terminal."""
        ts = self._timestamp()
        line = f"[{ts}] {text}"
        self._write(line)
        print(line, flush=True)
        self._broadcast("log", {"text": line})

    def thought(self, text: str) -> None:
        """
        Log the agent's complete text output (non-streaming fallback).

        This is the original non-streaming path. When streaming is active,
        use thought_chunk() + thought_done() instead.
        """
        ts = self._timestamp()
        # Truncate very long thoughts for the log file
        preview = text[:1000] + ("..." if len(text) > 1000 else "")
        line = f"[{ts}] [THOUGHT] {preview}"
        self._write(line)
        self._broadcast("thought", {"text": text})

    def thought_chunk(self, chunk: str) -> None:
        """
        Broadcast a streaming thought chunk to the frontend.

        Uses fire-and-forget (wait=False) to avoid slowing down the
        LLM stream processing. The frontend accumulates these chunks
        into a live-updating thought line.

        Args:
            chunk: A small piece of thought text from the LLM stream.
        """
        self._broadcast("thought_chunk", {"text": chunk}, wait=False)

    def thought_done(self, full_text: str) -> None:
        """
        Finalize a streaming thought: write to log file and notify frontend.

        Called after the LLM stream completes. The frontend replaces the
        live thought line with the final version.

        Args:
            full_text: The complete thought text.
        """
        ts = self._timestamp()
        preview = full_text[:1000] + ("..." if len(full_text) > 1000 else "")
        line = f"[{ts}] [THOUGHT] {preview}"
        self._write(line)
        self._broadcast("thought_done", {"text": full_text})

    def loading(self, text: str) -> None:
        """
        Broadcast a transient loading indicator to the frontend.

        The frontend displays this with animated dots and auto-removes it
        when the next real message arrives. Used for three phases:
        - "[LLM] Calling model"       : waiting for LLM response
        - "[LLM] Preparing tool calls" : LLM streaming tool arguments
        - "[TOOL] Executing <name>"    : tool being executed

        Also written to the log file for debugging, but the frontend
        treats it as ephemeral (disappears on next message).

        Args:
            text: The loading hint text (without trailing dots).
        """
        ts = self._timestamp()
        line = f"[{ts}] {text}..."
        self._write(line)
        print(line, flush=True)
        self._broadcast("loading", {"text": text})

    def tool_call(self, name: str, args: dict) -> None:
        """Log a tool invocation."""
        ts = self._timestamp()
        # Compact args for log line
        args_str = str(args)
        if len(args_str) > 200:
            args_str = args_str[:200] + "..."
        line = f"[{ts}] [TOOL] {name}({args_str})"
        self._write(line)
        print(line, flush=True)
        self._broadcast("tool_call", {"name": name, "args": args})

    def tool_result(self, result: str) -> None:
        """Log a tool execution result."""
        ts = self._timestamp()
        preview = result[:500] + ("..." if len(result) > 500 else "")
        line = f"[{ts}] [RESULT] {preview}"
        self._write(line)
        print(line, flush=True)
        self._broadcast("tool_result", {"text": result})

    def waiting(self, seconds: int) -> None:
        """Log the wait between rounds."""
        ts = self._timestamp()
        line = f"[{ts}] [WAIT] Next activation in {seconds}s..."
        self._write(line)
        print(line, flush=True)
        self._broadcast("status", {"status": "waiting", "next_in": seconds})


# =============================================================================
# Main Activation Loop
# =============================================================================

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

    Args:
        config:         Full configuration dict from ConfigManager.load().
        ws_manager:     WebSocket manager for broadcasting updates.
        stop_event:     Threading event to signal graceful shutdown.
        state_callback: Callback to update manager state (called with a dict
                        containing 'state', 'round', 'tools', 'summary').
        project_dir:    Awakener project root directory.
    """
    if stop_event is None:
        stop_event = threading.Event()

    # -- Resolve configuration --
    agent_config = config.get("agent", {})
    agent_home = agent_config.get("home", "/home/agent")
    model = agent_config.get("model", "deepseek/deepseek-chat")
    interval = agent_config.get("interval", 60)
    max_tool_calls = agent_config.get("max_tool_calls", 20)
    shell_timeout = agent_config.get("shell_timeout", 30)
    max_output = agent_config.get("max_output_chars", 4000)
    persona = agent_config.get("persona", "default")

    # API key: try environment variable based on model provider
    api_key = _resolve_api_key(model)

    # -- Initialize subsystems --
    data_dir = os.path.join(project_dir, "data")
    log_dir = os.path.join(data_dir, "logs")

    memory = MemoryManager(data_dir)
    logger = ActivatorLogger(log_dir, ws_manager, event_loop)

    # Ensure agent home directory exists
    os.makedirs(agent_home, exist_ok=True)

    # Resume round counter from previous session
    round_num = memory.get_last_round_number() + 1
    activator_pid = os.getpid()

    logger.info(f"[START] Activator started | Model: {model} | Home: {agent_home}")
    logger.info(f"[START] Interval: {interval}s | Tool budget: {max_tool_calls} | Resume at round {round_num}")

    if state_callback:
        state_callback({"state": "running", "round": round_num})

    # -- Main loop --
    while not stop_event.is_set():
        round_start_time = time.time()
        logger.round_start(round_num)

        if state_callback:
            state_callback({"state": "running", "round": round_num})

        # Build context messages
        system_msg = build_system_message(project_dir, persona)
        user_msg = build_user_message(round_num, max_tool_calls, memory)

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]

        logger.info(f"[CONTEXT] Persona: {persona} | Notes injected: {len(memory.get_recent_notes())}")

        # Create tool executor for this round
        tool_exec = ToolExecutor(
            agent_home=agent_home,
            project_dir=project_dir,
            activator_pid=activator_pid,
            timeout=shell_timeout,
            max_output=max_output,
            memory_manager=memory,
            current_round=round_num,
        )

        # Run one activation round
        result = run_round(
            messages=messages,
            tool_executor=tool_exec,
            model=model,
            api_key=api_key,
            normal_limit=max_tool_calls,
            logger=logger,
        )

        # Calculate duration
        duration = time.time() - round_start_time

        # Auto-record minimal notebook if agent forgot
        if not result.notebook_saved:
            logger.info("[WARN] Agent did not save notebook this round. Auto-recording minimal note.")
            memory.write_notebook(round_num, "(auto-saved: agent did not write notebook this round)")

        # Record to timeline
        memory.append_timeline(
            round_num=round_num,
            tools_used=result.tools_used,
            duration=duration,
            summary=result.summary[:300],
            notebook_saved=result.notebook_saved,
        )

        # Log round end
        logger.round_end(round_num, result.tools_used, duration, result.notebook_saved)

        if state_callback:
            state_callback({
                "state": "waiting",
                "round": round_num,
                "tools": result.tools_used,
                "summary": result.summary[:200],
            })

        # Advance round counter
        round_num += 1

        # -- Wait for interval (or stop_event) --
        if interval > 0 and not stop_event.is_set():
            logger.waiting(interval)
            # Use stop_event.wait() so we can be interrupted immediately
            stop_event.wait(timeout=interval)
        elif stop_event.is_set():
            break

    # -- Clean shutdown --
    logger.info("[STOP] Activator stopped gracefully")
    if state_callback:
        state_callback({"state": "idle", "round": round_num - 1})


# =============================================================================
# Helper: Resolve API Key
# =============================================================================

def _resolve_api_key(model: str) -> str | None:
    """
    Resolve the API key from environment variables based on model provider.

    LiteLLM auto-detects keys from env vars, but we explicitly check
    to provide better error messages and support custom key naming.

    The model format is "provider/model-name", e.g. "deepseek/deepseek-chat".

    Args:
        model: LiteLLM model identifier.

    Returns:
        API key string, or None (LiteLLM will try env vars itself).
    """
    provider = model.split("/")[0].upper() if "/" in model else model.upper()

    # Map provider names to environment variable names
    key_map = {
        "DEEPSEEK": "DEEPSEEK_API_KEY",
        "OPENAI": "OPENAI_API_KEY",
        "ANTHROPIC": "ANTHROPIC_API_KEY",
        "GOOGLE": "GOOGLE_API_KEY",
        "GEMINI": "GOOGLE_API_KEY",
    }

    env_name = key_map.get(provider)
    if env_name:
        return os.environ.get(env_name)

    return None
