"""
Awakener - Memory Manager
============================
Manages the agent's dual-layer memory system:

1. Notebook (data/notebook.jsonl)
   - Agent's subjective per-round notes.
   - Written by the agent via notebook_write tool.
   - Read by the agent via notebook_read tool.
   - Last N rounds auto-injected into the prompt each round.

2. Timeline (data/timeline.jsonl)
   - Activator's objective record, one entry per round.
   - Contains round number, timestamp, tool count, duration, summary.
   - Used by the web UI (not injected into the agent's prompt).

3. Inspiration (data/inspiration.txt)
   - One-way hints from the admin to the agent.
   - Read and cleared at the start of each round.
   - Replaces the old "inbox" concept.

File layout (under project data dir):
    data/
      notebook.jsonl     <- agent's per-round notes
      timeline.jsonl     <- activator's round history
      inspiration.txt    <- admin -> agent hints
      logs/
        2026-02-09.log   <- per-day run log (managed by loop.py)
"""

import json
import os
from datetime import datetime, timezone
from typing import Any


class MemoryManager:
    """
    Unified memory interface for the activator.

    All file I/O for notebook, timeline, and inspiration goes through
    this class. It ensures consistent formatting and error handling.

    Attributes:
        data_dir:        Path to the project's data/ directory.
        notebook_path:   Full path to notebook.jsonl.
        timeline_path:   Full path to timeline.jsonl.
        inspiration_path: Full path to inspiration.txt.
        _notebook_cache: In-memory cache of notebook entries (loaded once).
    """

    def __init__(self, data_dir: str):
        """
        Initialize the memory manager.

        Creates the data directory if it doesn't exist.

        Args:
            data_dir: Absolute path to the data/ directory.
        """
        self.data_dir = data_dir
        self.notebook_path = os.path.join(data_dir, "notebook.jsonl")
        self.timeline_path = os.path.join(data_dir, "timeline.jsonl")
        self.inspiration_path = os.path.join(data_dir, "inspiration.txt")

        os.makedirs(data_dir, exist_ok=True)

        # Cache: loaded on first access and kept in sync
        self._notebook_cache: list[dict] | None = None

    # =========================================================================
    # Notebook Operations
    # =========================================================================

    def _load_notebook(self) -> list[dict]:
        """
        Load all notebook entries from notebook.jsonl into memory.

        Each line is a JSON object with keys: round, timestamp, content.

        Returns:
            List of notebook entry dicts, ordered by round.
        """
        if self._notebook_cache is not None:
            return self._notebook_cache

        entries = []
        if os.path.exists(self.notebook_path):
            try:
                with open(self.notebook_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                entries.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
            except OSError:
                pass

        self._notebook_cache = entries
        return entries

    def write_notebook(self, round_num: int, content: str) -> None:
        """
        Append a new note for the given round to notebook.jsonl.

        If a note for this round already exists, it is overwritten
        (the old entry remains in the file, but the latest one wins
        when reading).

        Args:
            round_num: Current activation round number.
            content:   The agent's note text.
        """
        entry = {
            "round": round_num,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": content.strip(),
        }

        # Append to file
        try:
            with open(self.notebook_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

        # Update cache
        entries = self._load_notebook()
        entries.append(entry)

    def read_notebook(self, round_num: int) -> dict | None:
        """
        Read the notebook entry for a specific round.

        If multiple entries exist for the same round (due to overwrites),
        returns the latest one.

        Args:
            round_num: The round number to look up.

        Returns:
            The notebook entry dict, or None if not found.
        """
        entries = self._load_notebook()
        # Search from the end to get the latest entry for this round
        for entry in reversed(entries):
            if entry.get("round") == round_num:
                return entry
        return None

    def get_recent_notes(self, count: int = 3) -> list[dict]:
        """
        Get the most recent N notebook entries.

        Used by context.py to inject recent notes into the prompt.
        Deduplicates by round number (keeps latest entry per round).

        Args:
            count: Number of recent rounds to return.

        Returns:
            List of up to `count` notebook entries, oldest first.
        """
        entries = self._load_notebook()

        # Deduplicate: keep latest entry per round
        by_round: dict[int, dict] = {}
        for entry in entries:
            r = entry.get("round", 0)
            by_round[r] = entry

        # Sort by round number and take the last N
        sorted_entries = sorted(by_round.values(), key=lambda e: e.get("round", 0))
        return sorted_entries[-count:] if len(sorted_entries) > count else sorted_entries

    def get_last_round_number(self) -> int:
        """
        Get the highest round number recorded in the notebook.

        Used to resume the round counter after a restart.

        Returns:
            The last round number, or 0 if no entries exist.
        """
        entries = self._load_notebook()
        if not entries:
            # Also check timeline for round numbers
            return self._get_last_timeline_round()

        max_round = max(e.get("round", 0) for e in entries)
        timeline_round = self._get_last_timeline_round()
        return max(max_round, timeline_round)

    # =========================================================================
    # Timeline Operations
    # =========================================================================

    def append_timeline(
        self,
        round_num: int,
        tools_used: int,
        duration: float,
        summary: str,
        notebook_saved: bool = True,
    ) -> None:
        """
        Append one round's record to timeline.jsonl.

        Called by the activator loop after each round completes.

        Args:
            round_num:      The round number.
            tools_used:     Number of tool calls made.
            duration:       Round duration in seconds.
            summary:        Brief summary of what happened.
            notebook_saved: Whether the agent saved a notebook entry.
        """
        entry = {
            "round": round_num,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools_used": tools_used,
            "duration": round(duration, 1),
            "summary": summary,
            "notebook_saved": notebook_saved,
        }

        try:
            with open(self.timeline_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _get_last_timeline_round(self) -> int:
        """
        Get the highest round number from timeline.jsonl.

        Returns:
            The last round number, or 0 if no entries exist.
        """
        if not os.path.exists(self.timeline_path):
            return 0

        last_round = 0
        try:
            with open(self.timeline_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            r = entry.get("round", 0)
                            if r > last_round:
                                last_round = r
                        except json.JSONDecodeError:
                            continue
        except OSError:
            pass

        return last_round

    # =========================================================================
    # Inspiration Operations
    # =========================================================================

    def read_inspiration(self) -> str | None:
        """
        Read and clear the inspiration file.

        Called at the start of each activation round. The file content
        is returned and the file is deleted (one-time read).

        Returns:
            The inspiration text, or None if no inspiration pending.
        """
        if not os.path.exists(self.inspiration_path):
            return None

        try:
            with open(self.inspiration_path, "r", encoding="utf-8") as f:
                content = f.read().strip()

            if not content:
                # Empty file, remove it
                os.remove(self.inspiration_path)
                return None

            # Clear the file after reading
            os.remove(self.inspiration_path)
            return content

        except OSError:
            return None

    def write_inspiration(self, message: str) -> bool:
        """
        Write a message to the inspiration file.

        Called from the web UI when the admin sends a hint.
        Overwrites any existing inspiration.

        Args:
            message: The inspiration text.

        Returns:
            True if written successfully, False otherwise.
        """
        try:
            with open(self.inspiration_path, "w", encoding="utf-8") as f:
                f.write(message)
            return True
        except OSError:
            return False

    # =========================================================================
    # Bulk Read (for web API)
    # =========================================================================

    def get_all_notebook_entries(self) -> list[dict]:
        """
        Get all notebook entries. Used by the web API for the memory page.

        Returns:
            All notebook entries, deduplicated by round, sorted by round.
        """
        entries = self._load_notebook()

        by_round: dict[int, dict] = {}
        for entry in entries:
            r = entry.get("round", 0)
            by_round[r] = entry

        return sorted(by_round.values(), key=lambda e: e.get("round", 0))

    def get_all_timeline_entries(self) -> list[dict]:
        """
        Get all timeline entries. Used by the web API for the timeline page.

        Returns:
            All timeline entries, sorted by round.
        """
        entries = []
        if not os.path.exists(self.timeline_path):
            return entries

        try:
            with open(self.timeline_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            pass

        return entries
