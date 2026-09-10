"""Components that opt an entity into the spatial index."""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.ecs.component import StrictComponent


@dataclass(slots=True)
class SpatialTracked(StrictComponent):
    """Marks an entity for `SpatialIndexSystem` to track by world position.

    No physics body is required -- this is for gameplay entities a spatial
    query needs to find that have no pymunk shape at all (a pooled bullet,
    an AI perception target, an RTS-selectable unit).

    Attributes:
        mask: Bits a query must share at least one of to see this entity.
            Mirrors `physics.types.CollisionLayer`'s category/mask
            convention, but is otherwise unrelated to physics collision.
    """

    mask: int = 0xFFFFFFFF

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        StrictComponent.__init__(self)
