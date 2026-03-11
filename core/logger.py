"""
Awakener - Dual-Output Logger
================================
Writes to per-day log files AND broadcasts via WebSocket to the
web dashboard.  Used by all agent types (activator, auditor, chat).

Log files are stored in data/logs/ with filenames like 2026-02-09.log.
Each round starts with a clear separator header.
"""

import os
import asyncio
from datetime import datetime
from typing import Any


class ActivatorLogger:
    """
    Dual-output logger: writes to per-day log files AND broadcasts
    via WebSocket to the web dashboard.

    Attributes:
        log_dir:    Directory for log files (data/logs/).
        ws_manager: WebSocket manager for broadcasting (may be None).
        _loop:      asyncio event loop for WS broadcasts (may be None).
    """

    def __init__(self, log_dir: str, ws_manager: Any = None, event_loop: asyncio.AbstractEventLoop | None = None):
        self.log_dir = log_dir
        self.ws_manager = ws_manager
        self._loop = event_loop
        os.makedirs(log_dir, exist_ok=True)

    def _get_log_path(self) -> str:
        today = datetime.now().strftime("%Y-%m-%d")
        return os.path.join(self.log_dir, f"{today}.log")

    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _write(self, text: str) -> None:
        try:
            with open(self._get_log_path(), "a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass

    def _broadcast(self, msg_type: str, data: dict, wait: bool = True) -> None:
        if not self.ws_manager or not self._loop:
            return
        message = {"type": msg_type, "data": data}
        try:
            future = asyncio.run_coroutine_threadsafe(
                self.ws_manager.broadcast(message),
                self._loop,
            )
            if wait:
                future.result(timeout=5)
        except Exception:
            pass

    def round_start(self, round_num: int) -> None:
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

    def round_end(self, round_num: int, tools_used: int, duration: float) -> None:
        ts = self._timestamp()
        text = (
            f"[{ts}] [DONE] Round {round_num} complete | "
            f"Tools: {tools_used} | Time: {duration:.1f}s"
        )
        self._write(text)
        print(text, flush=True)
        self._broadcast("round", {
            "step": round_num,
            "event": "completed",
            "tools_used": tools_used,
            "duration": round(duration, 1),
        })

    def info(self, text: str) -> None:
        ts = self._timestamp()
        line = f"[{ts}] {text}"
        self._write(line)
        print(line, flush=True)
        self._broadcast("log", {"text": line})

    def thought(self, text: str) -> None:
        ts = self._timestamp()
        preview = text[:1000] + ("..." if len(text) > 1000 else "")
        line = f"[{ts}] [THOUGHT] {preview}"
        self._write(line)
        self._broadcast("thought", {"text": text})

    def thought_chunk(self, chunk: str) -> None:
        self._broadcast("thought_chunk", {"text": chunk}, wait=False)

    def thought_done(self, full_text: str) -> None:
        ts = self._timestamp()
        preview = full_text[:1000] + ("..." if len(full_text) > 1000 else "")
        line = f"[{ts}] [THOUGHT] {preview}"
        self._write(line)
        self._broadcast("thought_done", {"text": full_text})

    def loading(self, text: str) -> None:
        ts = self._timestamp()
        line = f"[{ts}] {text}..."
        self._write(line)
        print(line, flush=True)
        self._broadcast("loading", {"text": text})

    def loading_update(self, text: str) -> None:
        self._broadcast("loading_update", {"text": text}, wait=False)

    def tool_call(self, name: str, args: dict) -> None:
        ts = self._timestamp()
        args_str = str(args)
        if len(args_str) > 200:
            args_str = args_str[:200] + "..."
        line = f"[{ts}] [TOOL] {name}({args_str})"
        self._write(line)
        print(line, flush=True)
        self._broadcast("tool_call", {"name": name, "args": args})

    def tool_result(self, result: str) -> None:
        ts = self._timestamp()
        preview = result[:500] + ("..." if len(result) > 500 else "")
        line = f"[{ts}] [RESULT] {preview}"
        self._write(line)
        print(line, flush=True)
        self._broadcast("tool_result", {"text": result})

    def waiting(self, seconds: int) -> None:
        ts = self._timestamp()
        line = f"[{ts}] [WAIT] Next activation in {seconds}s..."
        self._write(line)
        print(line, flush=True)
        self._broadcast("status", {"status": "waiting", "next_in": seconds})
