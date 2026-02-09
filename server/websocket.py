"""
Awakener - WebSocket Manager
==============================
Manages WebSocket connections for real-time communication between
the management console frontend and the activator backend.

Message types (server -> client):
    - "log"          : Real-time log line from the activator
    - "status"       : Agent status change (running/stopped/waiting/error)
    - "round"        : New activation round started or completed
    - "thought"      : Agent's complete thought text (non-streaming fallback)
    - "thought_chunk": Streaming thought delta (partial text as LLM generates)
    - "thought_done" : Streaming thought finalized (complete text, ends stream)
    - "tool_call"    : Tool invocation details
    - "tool_result"  : Tool execution result

Message format:
    {
        "type": "log",
        "data": { ... },
        "timestamp": "2026-02-08T12:00:00"
    }

Usage:
    # In routes or manager, broadcast a message to all connected clients:
    await ws_manager.broadcast({"type": "log", "data": {"text": "hello"}})

    # In the WebSocket endpoint:
    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()  # Keep connection alive
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)
"""

import json
from datetime import datetime, timezone
from fastapi import WebSocket
from typing import Any


class WebSocketManager:
    """
    Manages multiple WebSocket client connections and message broadcasting.

    This is a simple in-memory manager suitable for single-server deployment.
    All connected clients receive all broadcast messages.

    Attributes:
        active_connections: Set of currently connected WebSocket instances.
    """

    def __init__(self):
        """Initialize with an empty connection set."""
        self.active_connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """
        Accept a new WebSocket connection and add it to the active set.

        Args:
            websocket: The incoming WebSocket connection to accept.
        """
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """
        Remove a WebSocket connection from the active set.

        Args:
            websocket: The WebSocket connection to remove.
        """
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """
        Send a message to all connected WebSocket clients.

        Automatically adds a timestamp to the message if not present.
        Silently removes clients that have disconnected.

        Args:
            message: Dictionary to send as JSON. Should include 'type' and 'data' keys.
        """
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()

        payload = json.dumps(message, ensure_ascii=False)

        # Track disconnected clients for cleanup
        disconnected = set()

        for ws in self.active_connections:
            try:
                await ws.send_text(payload)
            except Exception:
                # Client disconnected unexpectedly
                disconnected.add(ws)

        # Clean up disconnected clients
        self.active_connections -= disconnected

    async def send_log(self, text: str) -> None:
        """Convenience: broadcast a log message."""
        await self.broadcast({"type": "log", "data": {"text": text}})

    async def send_status(self, status: str, details: dict | None = None) -> None:
        """Convenience: broadcast an agent status update."""
        data = {"status": status}
        if details:
            data.update(details)
        await self.broadcast({"type": "status", "data": data})

    async def send_round(self, step: int, event: str, details: dict | None = None) -> None:
        """
        Convenience: broadcast a round lifecycle event.

        Args:
            step: Current activation round number.
            event: One of "started", "completed", "failed".
            details: Additional data (tool_count, elapsed, summary, etc.)
        """
        data = {"step": step, "event": event}
        if details:
            data.update(details)
        await self.broadcast({"type": "round", "data": data})

    @property
    def client_count(self) -> int:
        """Return the number of currently connected clients."""
        return len(self.active_connections)
