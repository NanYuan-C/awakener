"""
Awakener - Activator Process Manager
=======================================
Manages the lifecycle of the agent activator process.

The activator runs in a separate daemon thread, controlled by the
management console. This module provides start/stop/restart operations
and status queries.

Architecture:
    The manager holds a reference to the activator thread and communicates
    with the web frontend via the WebSocket manager. When the activator
    produces logs or status changes, they are pushed through WebSocket
    to all connected browser clients.

States:
    - "idle"     : Not started, waiting for user to click "Start"
    - "running"  : Activator is actively running an activation round
    - "waiting"  : Activator is between rounds, waiting for next interval
    - "stopping" : Stop requested, waiting for current round to finish
    - "error"    : Activator encountered a fatal error

Usage:
    manager = AgentManager(ws_manager, project_dir)
    await manager.start(config)   # Start activator in background thread
    await manager.stop()          # Gracefully stop after current round
    status = manager.status       # Get current status dict
"""

import os
import threading
from datetime import datetime, timezone
from typing import Any

from server.websocket import WebSocketManager


class AgentManager:
    """
    Controls the activator process lifecycle.

    This is the bridge between the web management console and the activator.
    It runs the activator in a daemon thread so the web server remains
    responsive, and communicates state changes through WebSocket.

    Attributes:
        ws:              WebSocket manager for broadcasting to frontend.
        project_dir:     Awakener project root directory.
        state:           Current state string.
        current_round:   Current activation round number.
        start_time:      When the activator was last started.
        total_rounds:    Total rounds completed in this session.
        last_round_summary: Summary text from the last completed round.
        last_round_tools:   Number of tools used in the last round.
    """

    def __init__(self, ws_manager: WebSocketManager, project_dir: str = ""):
        """
        Initialize the agent manager.

        Args:
            ws_manager:  WebSocket manager for real-time updates.
            project_dir: Awakener project root (for activator safety checks).
        """
        self.ws = ws_manager
        self.project_dir = project_dir
        self.state: str = "idle"
        self.current_round: int = 0
        self.start_time: str | None = None
        self.total_rounds: int = 0
        self.last_round_summary: str = ""
        self.last_round_tools: int = 0

        # Thread management
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def is_running(self) -> bool:
        """Check if the activator is currently running."""
        return self.state in ("running", "waiting")

    @property
    def status(self) -> dict[str, Any]:
        """
        Get a comprehensive status snapshot.

        Returns:
            Dict containing all current state information.
        """
        return {
            "state": self.state,
            "is_running": self.is_running,
            "current_round": self.current_round,
            "start_time": self.start_time,
            "total_rounds": self.total_rounds,
            "last_round_summary": self.last_round_summary,
            "last_round_tools": self.last_round_tools,
            "ws_clients": self.ws.client_count,
        }

    def _state_callback(self, update: dict) -> None:
        """
        Callback invoked by the activator loop to report state changes.

        This runs in the activator thread, so we update manager fields
        that the web API can read. No async calls here.

        Args:
            update: Dict with keys like 'state', 'round', 'tools', 'summary'.
        """
        if "state" in update:
            self.state = update["state"]
        if "round" in update:
            self.current_round = update["round"]
        if "tools" in update:
            self.last_round_tools = update["tools"]
            self.total_rounds += 1
        if "summary" in update:
            self.last_round_summary = update["summary"]

    def _run_activator(self, config: dict, event_loop) -> None:
        """
        Thread target: runs the activation loop.

        Imports and calls run_activation_loop from the activator package.
        If the loop exits (normally or due to error), the state is reset.

        Args:
            config:     Full configuration dict from ConfigManager.load().
            event_loop: The main asyncio event loop for WS broadcasts.
        """
        try:
            from activator import run_activation_loop

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
            # Notify frontend via WebSocket when thread actually exits
            try:
                import asyncio
                asyncio.run_coroutine_threadsafe(
                    self.ws.send_status(self.state, {
                        "message": "Agent stopped" if self.state == "idle" else "Agent error"
                    }),
                    event_loop,
                )
            except Exception:
                pass  # event loop may be closed

    async def start(self, config: dict) -> dict:
        """
        Start the activator in a background thread.

        Args:
            config: Full configuration dict (merged config.yaml + .env).

        Returns:
            Current status dict after starting.

        Raises:
            RuntimeError: If the activator is already running.
        """
        if self.is_running:
            raise RuntimeError("Agent is already running")

        # Prevent starting a new thread while the old one is still finishing
        if self._thread and self._thread.is_alive():
            raise RuntimeError(
                "Agent is still finishing its current round. "
                "Please wait a moment and try again."
            )

        self._stop_event.clear()
        self.state = "running"
        self.start_time = datetime.now(timezone.utc).isoformat()
        self.total_rounds = 0

        # Capture the current event loop for thread-safe WS broadcasts
        import asyncio
        event_loop = asyncio.get_running_loop()

        # Launch the activator in a daemon thread
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
        """
        Request the activator to stop gracefully.

        The activator will finish its current round before stopping.

        Returns:
            Current status dict.
        """
        if not self.is_running:
            self.state = "idle"
            return self.status

        self.state = "stopping"
        self._stop_event.set()

        await self.ws.send_status("stopping", {
            "message": "Stop command received, agent will stop after current round completes"
        })

        # Don't wait for thread — it will finish in the background and
        # broadcast "idle" via WebSocket when done. This gives instant
        # UI feedback to the user.
        return self.status

    async def restart(self, config: dict) -> dict:
        """
        Restart the activator with (potentially updated) configuration.

        Unlike stop(), restart must wait for the old thread to finish
        before starting a new one to avoid duplicate threads.

        Args:
            config: Full configuration dict.

        Returns:
            Current status dict after restart.
        """
        await self.stop()

        # Wait for old thread to actually exit (restart requires this)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=120)

        return await self.start(config)

    async def send_inspiration(self, message: str, data_dir: str) -> bool:
        """
        Send an inspiration message to the agent.

        The agent reads this at the start of its next activation round.
        Replaces the old "inbox" concept.

        Args:
            message:  The inspiration text.
            data_dir: Path to the data/ directory.

        Returns:
            True if the message was written successfully.
        """
        from activator.memory import MemoryManager

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
