"""Queue module for managing render commands."""

from pyguara.graphics.types import RenderCommand


class RenderQueue:
    """A specialized container that holds and sorts render commands."""

    def __init__(self) -> None:
        """Initialize an empty queue."""
        self._commands: list[RenderCommand] = []

    def push(self, cmd: RenderCommand) -> None:
        """Add a command to the buffer."""
        self._commands.append(cmd)

    def sort(self) -> None:
        """Sorts the queue in-place to ensure correct visual stacking.

        Sorting order:

        1. Layer: background to UI.
        2. Sort group (`Sprite.sort_group`): coarse ordering within the layer.
        3. Depth (`z_index`): a y-sorted command carries its world Y here.
        4. Material ID: groups commands at equal depth for the batcher.

        The sort is stable, so commands equal on every key keep their
        submission order.
        """
        self._commands.sort(
            key=lambda cmd: (cmd.layer, cmd.sort_group, cmd.z_index, cmd.material_id)
        )

    def clear(self) -> None:
        """Reset the queue for the next frame."""
        self._commands.clear()

    @property
    def commands(self) -> list[RenderCommand]:
        """Get the list of current commands."""
        return self._commands
