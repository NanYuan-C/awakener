"""
Awakener - Tool Registry
============================
Central registry for all agent tools.  Each tool file registers itself
on import via ``register_tool()``.  The engine and API query the registry
to build OpenAI-format schemas and dispatch calls.

Usage:
    from agents.tools import get_tools_schema, get_tool_handler
"""

from typing import Callable

_registry: dict[str, dict] = {}


def register_tool(
    name: str,
    description: str,
    parameters: dict,
    handler: Callable[..., str],
) -> None:
    """Register a tool for use by agents."""
    _registry[name] = {
        "name": name,
        "description": description,
        "parameters": parameters,
        "handler": handler,
    }


def get_tool_handler(name: str) -> Callable[..., str] | None:
    """Get the handler function for a registered tool."""
    entry = _registry.get(name)
    return entry["handler"] if entry else None


def get_tools_schema() -> list[dict]:
    """Return all registered tools in OpenAI function-calling format."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["parameters"],
            },
        }
        for t in _registry.values()
    ]


def get_tool_names() -> list[str]:
    """Return names of all registered tools."""
    return list(_registry.keys())
