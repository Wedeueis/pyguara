"""The attacker's damage-dealing volume.

A `Hitbox` entity also carries a `pyguara.physics.trigger_volume.TriggerVolume`
-- `Hitbox` is combat metadata riding alongside it, not a replacement for its
sensor-collider/entities-tracking machinery, which `TriggerSystem` already
builds and maintains. "Active frames" is just toggling that TriggerVolume's
own `active` field; nothing here adds a separate timer for it -- a game (or,
once it exists, an animation frame-event) flips it directly.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.ecs.component import StrictComponent
from pyguara.kits.stats.damage_type import DamageType


@dataclass(slots=True)
class Hitbox(StrictComponent):
    """Combat metadata for a `TriggerVolume`-carrying attack entity.

    Attributes:
        damage: Base damage, before crit/mitigation -- passed straight to
            `apply_damage()`.
        damage_type: See `kits.stats.DamageType`.
        is_critical: Whether this hit always crits (a simple flip; rolling
            a crit chance is the game's job, done before this is set).
        team: This attack's side. `HitboxSystem` refuses to damage a
            `Hurtbox` sharing the same non-None team -- friendly fire is
            never possible for two boxes both explicitly on a side. `None`
            (the default) means "hits everyone", including other `None`
            hurtboxes.
        attacker: Entity id to record as `DamageDealt.attacker`, if any.
        pierce_fraction: Forwarded to `apply_damage()`.
        invincibility_duration: Forwarded to `apply_damage()`.
    """

    damage: float = 0.0
    damage_type: DamageType = DamageType.PHYSICAL
    is_critical: bool = False
    team: str | None = None
    attacker: str | None = None
    pierce_fraction: float = 0.0
    invincibility_duration: float = 0.0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        StrictComponent.__init__(self)
