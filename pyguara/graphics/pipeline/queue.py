"""Queue module for managing render commands."""

from typing import List

from pyguara.graphics.types import RenderCommand


class RenderQueue:
    """A specialized container that holds and sorts render commands."""

    def __init__(self) -> None:
        """Initialize an empty queue."""
        self._commands: List[RenderCommand] = []

    def push(self, cmd: RenderCommand) -> None:
        """Add a command to the buffer."""
        self._commands.append(cmd)

    def sort(self) -> None:
        """
        Sorts the queue in-place to ensure correct visual stacking.

        Sorting Order:
        1. Layer (Background -> UI)
        2. Z-Index (Top-Down Y-Sort logic)
        """
        # Python's Timsort is stable and efficient for this
        self._commands.sort(key=lambda cmd: (cmd.layer, cmd.z_index))

    def clear(self) -> None:
        """Reset the queue for the next frame."""
        self._commands.clear()

    @property
    def commands(self) -> List[RenderCommand]:
        """Get the list of current commands."""
        return self._commands
