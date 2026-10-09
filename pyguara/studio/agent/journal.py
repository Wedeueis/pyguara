"""An append-only record of every edit, and who asked for it.

The reason this exists separately from the undo stack: the stack is a
*position* -- undo moves it, and what was undone leaves the undoable
history. The journal is a *log*, and an undo is another entry in it. When
an agent has made forty edits and something is wrong, the question is "what
did it do, in order" and the stack cannot answer it.

Written as JSON Lines, append-only, one object per entry. That format
rather than a single JSON document because the common operations are
"append one entry" and "read the tail", and a session that crashes
mid-write leaves every complete line before it readable.

Entries carry an `actor`, which is how a human edit, an agent's tool call
and a replayed script are told apart afterwards. Nothing enforces honesty
about it -- it is provenance, not a permission.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pyguara.log import get_logger

logger = get_logger(__name__)


class Actor(str, Enum):
    """Who asked for an entry.

    A `str` enum so it serializes as its own name with no encoder hook.
    """

    HUMAN = "human"
    """A person using the editor UI."""

    AGENT = "agent"
    """A coding agent, over MCP or the JSON-lines ops server."""

    SCRIPT = "script"
    """A script or test driving the ops surface."""

    SYSTEM = "system"
    """Studio itself -- a scene load, a session opening."""


@dataclass(frozen=True)
class JournalEntry:
    """One recorded action.

    Attributes:
        actor: Who asked for it.
        action: What was asked for -- an operation name, or `undo`/`redo`.
        detail: Structured specifics. For an edit this is the command's
            `describe()`, which carries the before and after values.
        ok: Whether it succeeded.
        error: Why it failed, when it did.
        timestamp: Unix time the entry was made.
        sequence: Position in the journal, from 1. Assigned by the journal,
            so an entry read back can be referred to unambiguously even
            when two share a timestamp.
    """

    actor: Actor
    action: str
    detail: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    error: str | None = None
    timestamp: float = field(default_factory=time.time)
    sequence: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Return the JSON-serializable form written to disk.

        Returns:
            The entry as a plain dict.
        """
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "actor": self.actor.value,
            "action": self.action,
            "ok": self.ok,
            "error": self.error,
            "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> JournalEntry:
        """Rebuild an entry read back from disk.

        Args:
            data: One decoded JSON line.

        Returns:
            The entry.
        """
        return cls(
            actor=Actor(data.get("actor", Actor.SYSTEM.value)),
            action=data.get("action", ""),
            detail=data.get("detail", {}),
            ok=bool(data.get("ok", True)),
            error=data.get("error"),
            timestamp=float(data.get("timestamp", 0.0)),
            sequence=int(data.get("sequence", 0)),
        )


class Journal:
    """Collects `JournalEntry`s, in memory and optionally on disk."""

    def __init__(self, path: Path | None = None, *, limit: int = 2000) -> None:
        """Create a journal.

        Args:
            path: A JSON Lines file to append to. None keeps the journal in
                memory only, which is what the tests and a throwaway
                session use.
            limit: How many entries to keep *in memory*. The file, when
                there is one, keeps everything -- the cap exists so a long
                session does not grow without bound, not to discard
                history.

        Raises:
            ValueError: If `limit` is not positive.
        """
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")

        self._path = path
        self._limit = limit
        self._entries: list[JournalEntry] = []
        self._sequence = 0

    @property
    def path(self) -> Path | None:
        """The file this journal appends to, or None when in memory only."""
        return self._path

    @property
    def entries(self) -> tuple[JournalEntry, ...]:
        """The retained entries, oldest first."""
        return tuple(self._entries)

    def __len__(self) -> int:
        """How many entries are retained in memory.

        Returns:
            The retained count, which is at most `limit`.
        """
        return len(self._entries)

    def record(
        self,
        actor: Actor,
        action: str,
        *,
        detail: dict[str, Any] | None = None,
        ok: bool = True,
        error: str | None = None,
    ) -> JournalEntry:
        """Append an entry.

        Args:
            actor: Who asked for it.
            action: What was asked for.
            detail: Structured specifics.
            ok: Whether it succeeded.
            error: Why it failed.

        Returns:
            The entry, with its sequence number assigned.
        """
        self._sequence += 1
        entry = JournalEntry(
            actor=actor,
            action=action,
            detail=detail or {},
            ok=ok,
            error=error,
            sequence=self._sequence,
        )

        self._entries.append(entry)
        while len(self._entries) > self._limit:
            self._entries.pop(0)

        self._append_to_file(entry)
        return entry

    def tail(self, count: int = 20) -> tuple[JournalEntry, ...]:
        """Return the most recent entries, oldest of them first.

        What an agent reads to see what it has already done, and what the
        journal panel shows.

        Args:
            count: How many entries to return.

        Returns:
            Up to `count` entries.

        Raises:
            ValueError: If `count` is negative.
        """
        if count < 0:
            raise ValueError(f"count must not be negative, got {count}")
        if count == 0:
            return ()
        return tuple(self._entries[-count:])

    def failures(self) -> tuple[JournalEntry, ...]:
        """Return every retained entry that failed.

        The first thing worth looking at when an agent's run went wrong.

        Returns:
            The failed entries, oldest first.
        """
        return tuple(entry for entry in self._entries if not entry.ok)

    def _append_to_file(self, entry: JournalEntry) -> None:
        """Write one line, or log why it could not be written.

        A journal that cannot be written must not take the edit down with
        it: the edit already happened, and losing the record of it is
        strictly better than losing the work.

        Args:
            entry: The entry to append.
        """
        if self._path is None:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry.to_dict()) + "\n")
        except OSError as exc:
            logger.warning(f"Could not append to the journal at {self._path}: {exc}")

    @staticmethod
    def read(path: Path) -> list[JournalEntry]:
        """Read a journal file back.

        Malformed lines are skipped with a warning rather than failing the
        read: a session killed mid-write leaves a partial last line, and
        everything before it is still worth having.

        Args:
            path: The JSON Lines file to read.

        Returns:
            The entries, in file order. Empty when the file is absent.
        """
        if not path.exists():
            return []

        entries: list[JournalEntry] = []
        with path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(JournalEntry.from_dict(json.loads(line)))
                except (json.JSONDecodeError, ValueError) as exc:
                    logger.warning(f"Skipping journal line {number} of {path}: {exc}")
        return entries
