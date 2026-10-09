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
        """
        Sorts the queue in-place to ensure correct visual stacking.

        Sorting order:

        1. **Layer** -- background to UI.
        2. **Sort group** -- coarse ordering within the layer, so a cluster
           of sprites can sort as one unit (`Sprite.sort_group`).
        3. **Depth** (`z_index`) -- a y-sorted command carries its world Y
           here, which is what makes 2.5D overlap work.
        4. **Material ID** -- groups by shader so the batcher has runs to
           find, among commands that are already at equal depth.

        Material used to be compared *before* depth, which meant two
        overlapping sprites with different materials drew in material order
        rather than depth order -- so y-sorting could not have worked at
        all in a scene with more than one material. Depth is a correctness
        constraint and batching is an optimisation, so depth wins; material
        still breaks ties, which is where the batching actually comes from
        (a tilemap row at one depth, a crowd of identical particles).

        Timsort is stable, so commands equal on every key keep their
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
