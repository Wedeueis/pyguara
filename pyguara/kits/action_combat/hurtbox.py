"""The defender's damage-receiving marker.

Not a shape of its own: `HitboxSystem` detects overlap through a
`Hitbox`'s `TriggerVolume` sensor against the target's solid
`Collider`, then checks for this component to confirm the target can
be damaged, and reads `team` from it. A `Hurtbox` with its own shape,
smaller than the movement collider, is not supported: the physics
backend does not resolve sensor-against-sensor overlap.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.ecs.component import StrictComponent


@dataclass(slots=True)
class Hurtbox(StrictComponent):
    """Marks an entity as a valid `Hitbox` damage target.

    Attributes:
        team: This entity's side. See `Hitbox.team` for the matching rule.
        radius: How far from its centre a projectile reaches it, added to the
            projectile's own `hit_radius` by `kits.projectiles`. 0, the default,
            treats it as a point, as before. A `Hitbox` overlap ignores it: that
            uses the solid `Collider`.
    """

    team: str | None = None
    radius: float = 0.0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        StrictComponent.__init__(self)
