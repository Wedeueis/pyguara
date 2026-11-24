"""Correição's own components, and the player's state.

The horde itself is made of engine components: `Transform`, `Sprite`,
`Animator` and `FlockingAgent`. The marker here only says which entities
are ants, so the combat pass and the spawner can find them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent


@dataclass(slots=True)
class Ant(StrictComponent):
    """Marker: this entity is one ant of the raid."""

    def __post_init__(self) -> None:
        """Run `StrictComponent`'s setup, which the generated `__init__` does not."""
        StrictComponent.__init__(self)


@dataclass
class PlayerState:
    """The calango: where it is, how hurt, and how it fights back.

    Plain data owned by the scene rather than a component, because there
    is exactly one and every system reads it.

    Attributes:
        position: Where the calango is in the world.
        heading: The last direction it moved in, for drawing it.
        health: Hit points; the calango regains them slowly.
        pulse_cooldown: Seconds until the next pulse.
        pulse_flash: Seconds left on the last pulse's ring, for drawing it.
        kills: Ants killed so far.
        bites: Ant bites taken so far.
        overruns: How many times the bites took all its health. It keeps
            fighting at full health, so the demo never stops.
    """

    position: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    heading: Vector2 = field(default_factory=lambda: Vector2(1, 0))
    health: float = 100.0
    pulse_cooldown: float = 1.0
    pulse_flash: float = 0.0
    kills: int = 0
    bites: int = 0
    overruns: int = 0
