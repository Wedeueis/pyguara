"""The event `apply_damage()` dispatches.

This is the event #28's kit-dependency notes point at: `kits/projectiles`
depends on `kits/action_combat`'s damage-event *type* specifically (not on
Hitbox/Hurtbox, which this kit doesn't build yet), and `kits/effects`
reacts to it -- and to whatever other kit dispatches its own events -- the
same way, through core event dispatch, never a direct import.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pyguara.kits.stats.damage_type import DamageType


@dataclass
class DamageDealt:
    """Fired by `apply_damage()` after mitigation, on every damage attempt.

    Fires even when `amount` ends up 0 (fully mitigated, or blocked by
    invincibility) -- a listener wanting "was this attack blocked" reads
    `amount == 0`, rather than needing a separate silence to mean the same
    thing.

    Attributes:
        target: The entity id that took the hit.
        attacker: The entity id responsible, if any (a projectile's owner,
            a melee attacker). None for untargeted damage (a hazard, a DoT
            with no live attacker). Named `attacker`, not `source`, to stay
            distinct from `Event.source` below -- "what dispatched this
            event" (typically whatever called `apply_damage()`), not "who
            dealt the damage".
        amount: Damage actually applied to `Health.current`, after
            mitigation -- 0 if the hit was fully mitigated or blocked by
            invincibility.
        damage_type: What kind of damage this was.
        is_critical: Whether the critical multiplier was applied.
        killed: Whether this hit brought `target`'s `Health.current` to 0.
    """

    target: str
    attacker: str | None
    amount: float
    damage_type: DamageType
    is_critical: bool
    killed: bool
    timestamp: float = field(default_factory=time.time)
    source: Any = None
