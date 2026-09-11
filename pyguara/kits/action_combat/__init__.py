"""The damage/health substrate of #28's action_combat kit.

Scoped to `Health`, `DamageDealt`, and the `apply_damage()` pipeline
(crit, mitigation via `kits/stats`, invincibility) -- Hitbox/Hurtbox with
active frames and team/faction filtering are deferred to a follow-up, per
the `/wayfinder` scoping discussion: they need real integration with
`pyguara.physics.trigger_volume`/animation, whereas this substrate is
self-contained and already what `kits/projectiles` depends on (#28 names
the damage-event *type* as the dependency, not Hitbox/Hurtbox).

Named `action_combat`, not `combat`, per #28: the eventual hitbox/
active-frame shape is one genre-specific flavor an RTS or turn-based game
wouldn't want.
"""

from pyguara.kits.action_combat.damage import (
    ARMOR_STAT,
    RESISTANCE_STAT,
    apply_damage,
)
from pyguara.kits.action_combat.events import DamageDealt
from pyguara.kits.action_combat.health import Health
from pyguara.kits.action_combat.system import HealthSystem

__all__ = [
    "ARMOR_STAT",
    "RESISTANCE_STAT",
    "DamageDealt",
    "Health",
    "HealthSystem",
    "apply_damage",
]
