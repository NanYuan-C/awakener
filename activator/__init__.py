"""
Awakener - Activator Package
===============================
The autonomous agent activation engine.

This package contains the core logic for the agent's activation loop:
    - loop.py    : Main activation loop entry point
    - agent.py   : LLM interaction and tool-calling loop (one round)
    - tools.py   : 5 tools with safety restrictions
    - memory.py  : Notebook (JSONL) + timeline + inspiration management
    - context.py : System/user prompt assembly

Usage:
    from activator import run_activation_loop

    # Called from server/manager.py in a background thread:
    run_activation_loop(
        config=config_dict,
        ws_manager=ws_manager,
        stop_event=threading_event,
        state_callback=callback_fn,
        project_dir="/opt/awakener",
    )
"""

from activator.loop import run_activation_loop

__all__ = ["run_activation_loop"]
