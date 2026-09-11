"""The defender's damage-receiving marker.

Not a shape of its own: `HitboxSystem` detects overlap through a
`Hitbox`'s `TriggerVolume` sensor against whatever solid `Collider` the
target already has, then checks for this component to confirm the target
is a valid damage recipient (and reads `team` off it). A `Hurtbox` with
its own independent shape, smaller than the target's movement collider,
isn't supported yet -- `pymunk_impl.py`'s sensor-vs-sensor overlap
resolution is an explicitly documented degenerate case
(`_sensor_entity_id()`), so giving `Hurtbox` its own sensor would hit
exactly that.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.ecs.component import StrictComponent


@dataclass(slots=True)
class Hurtbox(StrictComponent):
    """Marks an entity as a valid `Hitbox` damage target.

    Attributes:
        team: This entity's side. See `Hitbox.team` for the matching rule.
    """

    team: str | None = None

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        StrictComponent.__init__(self)
