"""
Awakener - Tool Executor
============================
Dispatches tool calls from the LLM to registered tool handlers,
applying stealth protection and path resolution.
"""

import os

from agents.tools import get_tool_handler
from agents.tools.stealth import build_stealth_keywords


class ToolExecutor:
    """
    Executes agent tools with stealth protection.

    Attributes:
        agent_home:       Agent's working directory.
        project_dir:      Awakener project root (cloaked zone).
        timeout:          Shell command timeout in seconds.
        max_output:       Max chars for tool output.
        stealth_keywords: Keywords for output filtering.
    """

    def __init__(
        self,
        agent_home: str,
        project_dir: str,
        activator_pid: int | None,
        timeout: int = 30,
        max_output: int = 4000,
        host_env: dict | None = None,
    ):
        self.agent_home = agent_home
        self.project_dir = project_dir
        self.timeout = timeout
        self.max_output = max_output
        self.stealth_keywords = build_stealth_keywords(
            project_dir, activator_pid, host_env,
        )

    def _resolve_path(self, path: str) -> str:
        """
        Resolve a file path.  Relative paths are resolved against
        ``agent_home`` (not the Python CWD) to prevent accidental
        access to the project directory.
        """
        if not path:
            return path
        if os.path.isabs(path):
            return path
        return os.path.join(self.agent_home, path)

    def execute(self, name: str, args: dict) -> str:
        """
        Dispatch and execute a tool by name.

        Args:
            name: Tool function name.
            args: Parsed argument dictionary from the LLM.

        Returns:
            Result string to return to the LLM.
        """
        if name == "shell_execute":
            handler = get_tool_handler("shell_execute")
            if not handler:
                return "(error: shell_execute tool not registered)"
            return handler(
                command=args.get("command", ""),
                agent_home=self.agent_home,
                project_dir=self.project_dir,
                timeout=self.timeout,
                max_output=self.max_output,
                stealth_keywords=self.stealth_keywords,
            )

        elif name == "read_file":
            handler = get_tool_handler("read_file")
            if not handler:
                return "(error: read_file tool not registered)"
            return handler(
                path=self._resolve_path(args.get("path", "")),
                project_dir=self.project_dir,
                max_output=self.max_output,
            )

        elif name == "write_file":
            handler = get_tool_handler("write_file")
            if not handler:
                return "(error: write_file tool not registered)"
            return handler(
                path=self._resolve_path(args.get("path", "")),
                content=args.get("content", ""),
                append=args.get("append", False),
                project_dir=self.project_dir,
            )

        elif name == "edit_file":
            handler = get_tool_handler("edit_file")
            if not handler:
                return "(error: edit_file tool not registered)"
            return handler(
                path=self._resolve_path(args.get("path", "")),
                old_str=args.get("old_str", ""),
                new_str=args.get("new_str", ""),
                project_dir=self.project_dir,
            )

        else:
            return f"(error: unknown tool '{name}')"
