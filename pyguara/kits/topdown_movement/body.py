"""Component for a top-down, 8-directional character.

Usage:
    entity.add_component(TopDownBody(separation_radius=10.0))

    A control or AI system sets `TopDownBody.velocity` directly each tick;
    `TopDownSystem` does the rest (movement, actor separation).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent


@dataclass(slots=True)
class TopDownBody(StrictComponent):
    """A character moved by `CharacterMover`, with actor-vs-actor separation.

    The top-down sibling of `CharacterBody`/`PlatformerController`: the same
    swept collide-and-slide against solids via `CharacterMover`, but no
    gravity, ground state, or jump -- an 8-dir top-down mover doesn't have
    any of those -- plus `separation_radius`, which `PlatformerController`
    has no equivalent of, since platformer characters don't gently push
    each other apart.

    Attributes:
        velocity: Current velocity in pixels/second, in world space.
            Nothing here integrates it from input; a control or AI system
            sets it directly each tick, the same way a `RigidBody`'s
            velocity is set directly rather than accumulated internally.
        separation_radius: Half of this actor's "personal space". Two
            actors are pushed apart by `TopDownSystem` once the distance
            between them is less than the sum of their two radii. Zero (the
            default) opts this actor out of separation entirely, in both
            directions -- it neither pushes others nor is pushed by them.
    """

    velocity: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    separation_radius: float = 0.0

    # Celeste-style sub-pixel accumulator, round-tripped through
    # CharacterMover.move() every tick. Never read by game code.
    _remainder: Vector2 = field(default_factory=lambda: Vector2(0, 0), repr=False)

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        StrictComponent.__init__(self)
