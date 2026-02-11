"""
Awakener - Memory Manager
============================
Manages the agent's memory system:

1. Timeline (data/timeline/<YYYY-MM-DD>.jsonl)
   - Activator's objective record, one entry per round.
   - Contains round number, timestamp, tool count, duration, summary,
     and a concise action_log (brief thoughts from tool-calling turns).
   - The full summary is displayed on the web timeline page.
   - The action_log is injected into the prompt for round continuity.
   - Per-day files for manageable sizes.

2. Inspiration (data/inspiration.txt)
   - One-way hints from the admin to the agent.
   - Read and cleared at the start of each round.

File layout (under project data dir):
    data/
      timeline/
        2026-02-09.jsonl <- activator's round history (one file per day)
      inspiration.txt    <- admin -> agent hints
      logs/
        2026-02-09.log   <- per-day run log (managed by loop.py)

Backward compatibility:
    If legacy single-file timeline.jsonl exists in data/,
    its entries are included when reading (but new writes go to the
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

    All file I/O for timeline and inspiration goes through this class.
    It ensures consistent formatting and error handling.

    Attributes:
        data_dir:         Path to the project's data/ directory.
        timeline_dir:     Path to the timeline/ directory.
        inspiration_path: Full path to inspiration.txt.
    """

    def __init__(self, data_dir: str):
        """
        Initialize the memory manager.

        Creates the data directory and subdirectories if they don't exist.

        Args:
            data_dir: Absolute path to the data/ directory.
        """
        self.data_dir = data_dir
        self.timeline_dir = os.path.join(data_dir, "timeline")
        self.inspiration_path = os.path.join(data_dir, "inspiration.txt")

        # Legacy single-file path (for backward compatibility reads)
        self._legacy_timeline = os.path.join(data_dir, "timeline.jsonl")

        os.makedirs(self.timeline_dir, exist_ok=True)

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

    def get_last_round_number(self) -> int:
        """
        Get the highest round number recorded in the timeline.

        Used to resume the round counter after a restart.

        Returns:
            The last round number, or 0 if no entries exist.
        """
        return self._get_last_timeline_round()

    # =========================================================================
    # Timeline Operations
    # =========================================================================

    def append_timeline(
        self,
        round_num: int,
        tools_used: int,
        duration: float,
        summary: str,
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

    # =========================================================================
    # Delete Operations (for web API)
    # =========================================================================

    def _delete_round_from_dir(self, directory: str, round_num: int, legacy_path: str | None = None) -> bool:
        """
        Delete all entries for a given round from JSONL files in a directory.

        Scans all .jsonl files (including legacy single-file), removes matching
        entries, and rewrites the files. Empty files are deleted.

        Args:
            directory:   Path to the per-day JSONL directory.
            round_num:   The round number to delete.
            legacy_path: Optional legacy single-file path.

        Returns:
            True if at least one entry was deleted.
        """
        found = False

        # Collect all files to check
        files_to_check = []
        if legacy_path and os.path.exists(legacy_path):
            files_to_check.append(legacy_path)

        import glob as glob_mod
        pattern = os.path.join(directory, "*.jsonl")
        files_to_check.extend(sorted(glob_mod.glob(pattern)))

        for filepath in files_to_check:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                new_lines = []
                for line in lines:
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue
                    try:
                        entry = json.loads(line_stripped)
                        if entry.get("round") == round_num:
                            found = True
                            continue  # Skip this entry (delete it)
                    except json.JSONDecodeError:
                        pass
                    new_lines.append(line)

                if found:
                    if new_lines:
                        with open(filepath, "w", encoding="utf-8") as f:
                            f.writelines(new_lines)
                    else:
                        # File is now empty, remove it
                        os.remove(filepath)
            except OSError:
                continue

        return found

    def delete_round(self, round_num: int) -> dict:
        """
        Cascade-delete all data for a given round: timeline and logs.

        This is the main entry point for the web API delete operation.
        Deleting from the timeline page removes all associated data so
        the agent won't see stale entries on next startup.

        Args:
            round_num: The round number to delete.

        Returns:
            Dict with keys 'timeline', 'logs' indicating
            whether each type of data was found and deleted.
        """
        result = {
            "timeline": self._delete_round_from_dir(
                self.timeline_dir, round_num, self._legacy_timeline
            ),
            "logs": self._delete_round_from_logs(round_num),
        }
        return result

    def _delete_round_from_logs(self, round_num: int) -> bool:
        """
        Delete log entries for a specific round from per-day log files.

        Log files use round separators like:
            ==================================================
            Round 7 | 2026-02-10 21:35:23
            ==================================================

        Everything from one separator to the next belongs to that round.

        Args:
            round_num: The round number whose log section to remove.

        Returns:
            True if log entries were found and deleted.
        """
        import re

        log_dir = os.path.join(self.data_dir, "logs")
        if not os.path.isdir(log_dir):
            return False

        found = False
        # Round separator pattern: line starting with "Round N |"
        separator = re.compile(r"^={10,}$")
        round_header = re.compile(rf"^Round\s+{round_num}\s+\|")

        for filename in sorted(os.listdir(log_dir)):
            if not filename.endswith(".log"):
                continue

            filepath = os.path.join(log_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
            except OSError:
                continue

            # Find and remove the round's section
            new_lines = []
            skip = False
            i = 0

            while i < len(lines):
                line = lines[i]

                # Check if this is a separator + round header block
                if separator.match(line.strip()) and i + 1 < len(lines):
                    next_line = lines[i + 1]
                    if round_header.match(next_line.strip()):
                        # This is the target round — skip until next separator block
                        found = True
                        skip = True
                        i += 1  # Skip the separator line
                        continue

                    if skip:
                        # We hit the NEXT round's separator — stop skipping
                        skip = False

                if not skip:
                    new_lines.append(line)
                i += 1

            if found:
                if any(l.strip() for l in new_lines):
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                else:
                    os.remove(filepath)

        return found

    # =========================================================================
    # Bulk Read (for web API)
    # =========================================================================

    def get_all_timeline_entries(self) -> list[dict]:
        """
        Get all timeline entries. Used by the web API for the timeline page.

        Returns:
            All timeline entries, in chronological order.
        """
        return self._read_all_from_dir(self.timeline_dir, self._legacy_timeline)
