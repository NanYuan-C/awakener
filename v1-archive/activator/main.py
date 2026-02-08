#!/usr/bin/env python3
"""
Awakener - Main Activator
The heartbeat that keeps the agent alive.

Usage:
    python main.py                  # Use default config
    python main.py -c /path/to.json # Use custom config
"""

import json
import time
import os
import sys
import argparse
import threading
from datetime import datetime

# Ensure activator directory is in path
ACTIVATOR_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(ACTIVATOR_DIR)
sys.path.insert(0, ACTIVATOR_DIR)

from agent import run_activation


# ── Logger ────────────────────────────────────────────────────────────────

class Logger:
    """Dual output: terminal + log file."""

    def __init__(self, log_path: str):
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        self.log_file = open(log_path, "a", encoding="utf-8")

    def _write(self, text: str):
        print(text, flush=True)
        self.log_file.write(text + "\n")
        self.log_file.flush()

    def separator(self, step: int):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._write(f"\n{'=' * 55}")
        self._write(f"  Round {step} | {ts}")
        self._write(f"{'=' * 55}")

    def info(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._write(f"[{ts}] {msg}")

    def thought(self, text: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._write(f"[{ts}] [AGENT] {text}")

    def tool_call(self, name: str, args: dict):
        args_str = json.dumps(args, ensure_ascii=False)
        if len(args_str) > 200:
            args_str = args_str[:200] + "..."
        ts = datetime.now().strftime("%H:%M:%S")
        self._write(f"[{ts}] [TOOL]  {name}({args_str})")

    def tool_result(self, result: str):
        display = result[:500] if len(result) <= 500 else result[:500] + "..."
        lines = display.split("\n")
        ts = datetime.now().strftime("%H:%M:%S")
        if len(lines) > 1:
            self._write(f"[{ts}] [RESULT]")
            for line in lines[:20]:
                self._write(f"         {line}")
            if len(lines) > 20:
                self._write(f"         ... ({len(lines) - 20} more lines)")
        else:
            self._write(f"[{ts}] [RESULT] {display}")

    def error(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self._write(f"[{ts}] [ERROR] {msg}")

    def close(self):
        self.log_file.close()


# ── Config Loading ────────────────────────────────────────────────────────

def load_config(config_path: str) -> dict:
    """Load and validate configuration."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    required = ["model", "api_key", "agent_home"]
    for key in required:
        if key not in config or not config[key]:
            raise ValueError(f"Missing required config: {key}")
    if config["api_key"] == "sk-your-api-key-here":
        raise ValueError("Please set your API key in config.json")

    return config


# ── Timeline Recording ────────────────────────────────────────────────────

def get_last_step(log_dir: str) -> int:
    """Read timeline.jsonl to find the last step number. Returns 0 if empty."""
    timeline_path = os.path.join(log_dir, "timeline.jsonl")
    last_step = 0
    try:
        with open(timeline_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    record = json.loads(line)
                    last_step = record.get("step", last_step)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return last_step


def append_timeline(log_dir: str, step: int, tool_count: int, elapsed: float, summary: str):
    """Append one round's record to timeline.jsonl."""
    record = {
        "step": step,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tools_used": tool_count,
        "elapsed_seconds": round(elapsed, 1),
        "summary": summary[:300],
    }
    timeline_path = os.path.join(log_dir, "timeline.jsonl")
    with open(timeline_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Recent Memories Manager ───────────────────────────────────────────────

class RecentMemories:
    """Rolling window of recent round summaries."""

    def __init__(self, max_rounds: int = 3):
        self.max_rounds = max_rounds
        self.memories: list[dict] = []

    def add(self, step: int, content: str):
        """Add a new round's summary."""
        self.memories.append({
            "step": step,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "content": content,
        })
        # Trim to max
        if len(self.memories) > self.max_rounds:
            self.memories = self.memories[-self.max_rounds:]

    def get_all(self) -> list[dict]:
        """Get all recent memories."""
        return list(self.memories)


# ── Shared State (for web dashboard) ─────────────────────────────────────

class ActivatorState:
    """Shared state between main loop and web dashboard."""

    def __init__(self):
        self.current_step = 0
        self.status = "starting"  # starting | running | waiting | stopped
        self.last_round_time = None
        self.last_round_tools = 0
        self.last_round_summary = ""
        self.next_activation_at = None
        self.total_rounds = 0
        self.config = {}
        self.log_path = ""
        self.timeline_path = ""
        self.notebook_path = ""

    def to_dict(self) -> dict:
        return {
            "current_step": self.current_step,
            "status": self.status,
            "last_round_time": self.last_round_time,
            "last_round_tools": self.last_round_tools,
            "last_round_summary": self.last_round_summary,
            "next_activation_at": self.next_activation_at,
            "total_rounds": self.total_rounds,
            "model": self.config.get("model", ""),
            "interval": self.config.get("interval", 60),
        }


# ── Main Loop ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Awakener - Autonomous Agent Activator")
    parser.add_argument("-c", "--config", default=os.path.join(PROJECT_DIR, "config.json"),
                        help="Path to config.json")
    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    agent_home = config["agent_home"]
    log_dir = os.path.join(PROJECT_DIR, "logs")
    
    # Create timestamped log file
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(log_dir, f"activator-{timestamp}.log")

    # Ensure directories exist
    os.makedirs(agent_home, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    # Initialize
    logger = Logger(log_path)
    ctx_config = config.get("context_window", {})
    recent_memories = RecentMemories(max_rounds=ctx_config.get("recent_rounds", 3))

    # Shared state for web dashboard
    state = ActivatorState()
    state.config = config
    state.log_path = log_path
    state.timeline_path = os.path.join(log_dir, "timeline.jsonl")
    state.notebook_path = os.path.join(agent_home, config.get("notebook_file", "notebook.md"))

    # Start web dashboard if enabled
    web_config = config.get("web_dashboard", {})
    if web_config.get("enabled", False):
        try:
            from web import start_dashboard
            dashboard_thread = threading.Thread(
                target=start_dashboard,
                args=(state, web_config),
                daemon=True,
            )
            dashboard_thread.start()
            logger.info(f"[WEB] Dashboard started on port {web_config.get('port', 8080)}")
        except Exception as e:
            logger.error(f"[WEB] Failed to start dashboard: {e}")

    # Startup banner
    logger.info("=" * 55)
    logger.info("  AWAKENER - Autonomous Agent Activator")
    logger.info("=" * 55)
    logger.info(f"Model     : {config['model']}")
    logger.info(f"Agent home: {agent_home}")
    logger.info(f"Log file  : {os.path.basename(log_path)}")
    logger.info(f"Interval  : {config.get('interval', 60)}s")
    logger.info(f"Max tools : {config.get('max_tool_calls_per_activation', 20)} per round")
    logger.info(f"Memory    : last {ctx_config.get('recent_rounds', 3)} rounds")

    # Resume step counter from timeline
    step = get_last_step(log_dir)
    if step > 0:
        logger.info(f"Resuming from step {step}")

    while True:
        step += 1
        logger.separator(step)

        state.current_step = step
        state.status = "running"

        # Run one activation
        start_time = time.time()
        try:
            tool_count, round_summary = run_activation(
                config=config,
                project_dir=PROJECT_DIR,
                step=step,
                recent_memories=recent_memories.get_all(),
                logger=logger,
            )
            elapsed = time.time() - start_time

            # Update recent memories
            recent_memories.add(step, round_summary)

            # Record to timeline
            append_timeline(log_dir, step, tool_count, elapsed, round_summary)

            # Update shared state
            state.last_round_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            state.last_round_tools = tool_count
            state.last_round_summary = round_summary
            state.total_rounds = step

            logger.info(f"[DONE] Tools: {tool_count} | Time: {elapsed:.1f}s")

        except KeyboardInterrupt:
            raise
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"Round failed ({elapsed:.1f}s): {type(e).__name__}: {e}")

        # Wait for next round
        interval = config.get("interval", 60)
        state.status = "waiting"
        state.next_activation_at = datetime.fromtimestamp(
            time.time() + interval
        ).strftime("%Y-%m-%d %H:%M:%S")

        logger.info(f"[WAIT] Next activation in {interval}s...")

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("[STOP] Stopped by user (Ctrl+C)")
            state.status = "stopped"
            break

    logger.close()


if __name__ == "__main__":
    main()
