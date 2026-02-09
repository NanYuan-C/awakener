"""
Awakener - Memory Manager
============================
Manages the agent's dual-layer memory system:

1. Notebook (data/notebook/<YYYY-MM-DD>.jsonl)
   - Agent's subjective per-round notes.
   - Written by the agent via notebook_write tool.
   - Read by the agent via notebook_read tool.
   - Last N rounds auto-injected into the prompt each round.
   - Per-day files for manageable sizes.

2. Timeline (data/timeline/<YYYY-MM-DD>.jsonl)
   - Activator's objective record, one entry per round.
   - Contains round number, timestamp, tool count, duration, summary,
     and a concise action_log (brief thoughts from tool-calling turns).
   - The full summary is displayed on the web timeline page.
   - The action_log is injected into the prompt for round continuity.
   - Per-day files for manageable sizes.

3. Inspiration (data/inspiration.txt)
   - One-way hints from the admin to the agent.
   - Read and cleared at the start of each round.
   - Replaces the old "inbox" concept.

File layout (under project data dir):
    data/
      notebook/
        2026-02-09.jsonl <- agent's per-round notes (one file per day)
      timeline/
        2026-02-09.jsonl <- activator's round history (one file per day)
      inspiration.txt    <- admin -> agent hints
      logs/
        2026-02-09.log   <- per-day run log (managed by loop.py)

Backward compatibility:
    If legacy single-file notebook.jsonl or timeline.jsonl exist in data/,
    their entries are included when reading (but new writes go to the
    per-day directory).
"""

import glob
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

        Creates the data directory and subdirectories if they don't exist.

        Args:
            data_dir: Absolute path to the data/ directory.
        """
        self.data_dir = data_dir
        self.notebook_dir = os.path.join(data_dir, "notebook")
        self.timeline_dir = os.path.join(data_dir, "timeline")
        self.inspiration_path = os.path.join(data_dir, "inspiration.txt")

        # Legacy single-file paths (for backward compatibility reads)
        self._legacy_notebook = os.path.join(data_dir, "notebook.jsonl")
        self._legacy_timeline = os.path.join(data_dir, "timeline.jsonl")

        os.makedirs(self.notebook_dir, exist_ok=True)
        os.makedirs(self.timeline_dir, exist_ok=True)

        # Cache: loaded on first access and kept in sync
        self._notebook_cache: list[dict] | None = None

    # =========================================================================
    # Helpers: per-day file I/O
    # =========================================================================

    @staticmethod
    def _today_filename() -> str:
        """Return today's date as YYYY-MM-DD.jsonl."""
        return datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl"

    @staticmethod
    def _read_jsonl_file(path: str) -> list[dict]:
        """Read all JSON objects from a single .jsonl file."""
        entries = []
        if not os.path.exists(path):
            return entries
        try:
            with open(path, "r", encoding="utf-8") as f:
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

    def _read_all_from_dir(self, directory: str, legacy_path: str | None = None) -> list[dict]:
        """
        Read all .jsonl files in a directory (sorted by filename = date).

        Also includes entries from the legacy single-file if it exists.

        Returns:
            All entries in chronological order.
        """
        entries = []

        # Legacy single-file (if present)
        if legacy_path and os.path.exists(legacy_path):
            entries.extend(self._read_jsonl_file(legacy_path))

        # Per-day files, sorted by date
        pattern = os.path.join(directory, "*.jsonl")
        for filepath in sorted(glob.glob(pattern)):
            entries.extend(self._read_jsonl_file(filepath))

        return entries

    # =========================================================================
    # Notebook Operations
    # =========================================================================

    def _load_notebook(self) -> list[dict]:
        """
        Load all notebook entries from per-day files into memory.

        Each line is a JSON object with keys: round, timestamp, content.

        Returns:
            List of notebook entry dicts, ordered chronologically.
        """
        if self._notebook_cache is not None:
            return self._notebook_cache

        self._notebook_cache = self._read_all_from_dir(
            self.notebook_dir, self._legacy_notebook
        )
        return self._notebook_cache

    def write_notebook(self, round_num: int, content: str) -> None:
        """
        Append a new note for the given round to today's notebook file.

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

        # Append to today's file
        filepath = os.path.join(self.notebook_dir, self._today_filename())
        try:
            with open(filepath, "a", encoding="utf-8") as f:
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
        action_log: str = "",
    ) -> None:
        """
        Append one round's record to today's timeline file.

        Called by the activator loop after each round completes.

        Args:
            round_num:      The round number.
            tools_used:     Number of tool calls made.
            duration:       Round duration in seconds.
            summary:        Full summary of the agent's thoughts and outputs
                            (displayed on the timeline web page).
            notebook_saved: Whether the agent saved a notebook entry.
            action_log:     Concise action log — only the brief thoughts from
                            tool-calling turns (injected into next round's prompt).
        """
        entry = {
            "round": round_num,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tools_used": tools_used,
            "duration": round(duration, 1),
            "summary": summary,
            "action_log": action_log,
            "notebook_saved": notebook_saved,
        }

        filepath = os.path.join(self.timeline_dir, self._today_filename())
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def get_recent_timeline(self, count: int = 1) -> list[dict]:
        """
        Get the most recent N timeline entries.

        Used by context.py to inject the agent's recent activity log
        into the prompt so it can resume work without re-exploring.

        Args:
            count: Number of recent entries to return.

        Returns:
            List of up to ``count`` timeline entries, oldest first.
        """
        entries = self._read_all_from_dir(self.timeline_dir, self._legacy_timeline)
        return entries[-count:] if len(entries) > count else entries

    def _get_last_timeline_round(self) -> int:
        """
        Get the highest round number from all timeline files.

        Returns:
            The last round number, or 0 if no entries exist.
        """
        entries = self._read_all_from_dir(self.timeline_dir, self._legacy_timeline)
        if not entries:
            return 0
        return max(e.get("round", 0) for e in entries)

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
            All timeline entries, in chronological order.
        """
        return self._read_all_from_dir(self.timeline_dir, self._legacy_timeline)
