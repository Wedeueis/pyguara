"""The action_combat kit: damage and health, plus Hitbox and Hurtbox.

`Health`, `DamageDealt` and the `apply_damage()` pipeline (crit,
mitigation via `kits/stats`, invincibility) stand alone;
`kits/projectiles` depends on them.

`Hitbox`, `Hurtbox` and `HitboxSystem` detect hits. A `Hitbox` entity
carries a `TriggerVolume`, and "active frames" is that volume's
`active` field, set by the game or by `ActiveFrameSystem` from
`AnimationFrameEvent`. A `Hurtbox` has no shape: overlap is detected
against the target's solid `Collider`.
"""

from pyguara.kits.action_combat.active_frame import ActiveFrameWindow
from pyguara.kits.action_combat.active_frame_system import ActiveFrameSystem
from pyguara.kits.action_combat.damage import (
    ARMOR_STAT,
    RESISTANCE_STAT,
    apply_damage,
)
from pyguara.kits.action_combat.events import DamageDealt
from pyguara.kits.action_combat.health import Health
from pyguara.kits.action_combat.hitbox import Hitbox
from pyguara.kits.action_combat.hitbox_system import HitboxSystem
from pyguara.kits.action_combat.hurtbox import Hurtbox
from pyguara.kits.action_combat.system import HealthSystem

__all__ = [
    "ARMOR_STAT",
    "RESISTANCE_STAT",
    "ActiveFrameSystem",
    "ActiveFrameWindow",
    "DamageDealt",
    "Health",
    "HealthSystem",
    "Hitbox",
    "HitboxSystem",
    "Hurtbox",
    "apply_damage",
]
