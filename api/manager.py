"""
Awakener - Activator Process Manager
=======================================
Manages the lifecycle of the agent activator process.

States:
    - "idle"     : Not started
    - "running"  : Actively running an activation round
    - "waiting"  : Between rounds, waiting for next interval
    - "stopping" : Stop requested, waiting for current round to finish
    - "error"    : Encountered a fatal error
"""

import os
import threading
from datetime import datetime, timezone
from typing import Any

from api.ws.connection import WebSocketManager


class AgentManager:
    """Controls the activator process lifecycle."""

    def __init__(self, ws_manager: WebSocketManager, project_dir: str = ""):
        self.ws = ws_manager
        self.project_dir = project_dir
        self.state: str = "idle"
        self.current_round: int = 0
        self.start_time: str | None = None
        self.total_rounds: int = 0
        self.last_round_summary: str = ""
        self.last_round_tools: int = 0

        self.round_start_time: str | None = None
        self.round_tools_used: int = 0

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def is_running(self) -> bool:
        return self.state in ("running", "waiting")

    @property
    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "is_running": self.is_running,
            "current_round": self.current_round,
            "start_time": self.start_time,
            "total_rounds": self.total_rounds,
            "last_round_summary": self.last_round_summary,
            "last_round_tools": self.last_round_tools,
            "round_start_time": self.round_start_time,
            "round_tools_used": self.round_tools_used,
            "ws_clients": self.ws.client_count,
        }

    def _state_callback(self, update: dict) -> None:
        if "state" in update:
            self.state = update["state"]
        if "round" in update:
            self.current_round = update["round"]
        if "tools" in update:
            self.last_round_tools = update["tools"]
            self.total_rounds += 1
        if "summary" in update:
            self.last_round_summary = update["summary"]
        if "round_start_time" in update:
            self.round_start_time = update["round_start_time"]
        if "round_tools_used" in update:
            self.round_tools_used = update["round_tools_used"]

    def _run_activator(self, config: dict, event_loop) -> None:
        try:
            from agents.activator import run_activation_loop

            run_activation_loop(
                config=config,
                ws_manager=self.ws,
                stop_event=self._stop_event,
                state_callback=self._state_callback,
                project_dir=self.project_dir,
                event_loop=event_loop,
            )
        except Exception as e:
            self.state = "error"
            self.last_round_summary = f"Fatal error: {e}"
            print(f"[FATAL] Activator error: {e}", flush=True)
        finally:
            if self.state != "error":
                self.state = "idle"
            try:
                import asyncio
                asyncio.run_coroutine_threadsafe(
                    self.ws.send_status(self.state, {
                        "message": "Agent stopped" if self.state == "idle" else "Agent error"
                    }),
                    event_loop,
                )
            except Exception:
                pass

    async def start(self, config: dict) -> dict:
        if self.is_running:
            raise RuntimeError("Agent is already running")
        if self._thread and self._thread.is_alive():
            raise RuntimeError(
                "Agent is still finishing its current round. "
                "Please wait a moment and try again."
            )

        self._stop_event.clear()
        self.state = "running"
        self.start_time = datetime.now(timezone.utc).isoformat()
        self.total_rounds = 0

        import asyncio
        event_loop = asyncio.get_running_loop()

        self._thread = threading.Thread(
            target=self._run_activator,
            args=(config, event_loop),
            daemon=True,
            name="awakener-activator",
        )
        self._thread.start()

        await self.ws.send_status("running", {"message": "Agent started"})
        return self.status

    async def stop(self) -> dict:
        if not self.is_running:
            self.state = "idle"
            return self.status

        self.state = "stopping"
        self._stop_event.set()

        await self.ws.send_status("stopping", {
            "message": "Stop command received, agent will stop after current round completes"
        })
        return self.status

    async def restart(self, config: dict) -> dict:
        await self.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=120)
        return await self.start(config)

    async def send_inspiration(self, message: str, data_dir: str) -> bool:
        from services.memory import MemoryManager

        try:
            memory = MemoryManager(data_dir)
            success = memory.write_inspiration(message)
            if success:
                await self.ws.send_log(
                    f"[INSPIRATION] Sent to agent: {message[:100]}"
                )
            return success
        except Exception as e:
            await self.ws.send_log(f"[ERROR] Failed to write inspiration: {e}")
            return False
