"""Blackboard system for sharing data between AI nodes and states."""

from typing import Any, Dict


class Blackboard:
    """
    A shared memory container for AI decision making.

    Allows different parts of an AI (e.g., nodes in a Behavior Tree or states
    in an FSM) to read and write shared data without tight coupling.
    """

    def __init__(self) -> None:
        """Initialize the blackboard."""
        self._data: Dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        """Set a value in the blackboard."""
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from the blackboard."""
        return self._data.get(key, default)

    def has(self, key: str) -> bool:
        """Check if a key exists."""
        return key in self._data

    def clear(self) -> None:
        """Clear all data."""
        self._data.clear()
