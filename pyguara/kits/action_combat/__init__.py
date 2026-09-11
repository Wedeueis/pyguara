"""#28's action_combat kit: damage/health substrate plus Hitbox/Hurtbox.

`Health`, `DamageDealt`, and the `apply_damage()` pipeline (crit,
mitigation via `kits/stats`, invincibility) are the self-contained
substrate -- already what `kits/projectiles` depends on (#28 names the
damage-event *type* as the dependency, not Hitbox/Hurtbox).

`Hitbox`/`Hurtbox`/`HitboxSystem` are the collision-detection half, built
on `pyguara.physics.trigger_volume.TriggerVolume` (a `Hitbox` entity also
carries one) rather than new sensor/collision machinery. "Active frames"
is just toggling that `TriggerVolume`'s own `active` field -- a game
flips it directly, or, on an entity that opts in with
`ActiveFrameWindow`, `ActiveFrameSystem` flips it from
`pyguara.graphics.events.AnimationFrameEvent` instead -- no separate
timer either way. `Hurtbox` has no shape of its own -- overlap is
detected against the target's existing solid `Collider`, since a second,
independently-shaped sensor would hit `pymunk_impl.py`'s documented
sensor-vs-sensor degenerate case.

Named `action_combat`, not `combat`, per #28: the hitbox/active-frame
shape here is one genre-specific flavor an RTS or turn-based game
wouldn't want.
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
