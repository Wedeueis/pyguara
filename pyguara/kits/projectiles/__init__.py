"""#28's projectiles kit: pooled projectile entities on core spatial.

Not ECS entities, and not `Hitbox`/`TriggerVolume`-based -- `ProjectileSystem`
mirrors `ParticleSystem`'s plain-object pool and checks hits against the
shared spatial hash (#98) directly, matching that data structure's own
"shooter bullets" design rationale (cheap enough for the volume a
shmup-style bullet pattern produces; physics-body-per-bullet is not).
On a hit, calls `kits.action_combat.apply_damage()` the same way `Hitbox`
does, against any candidate carrying `Hurtbox` + `Health`.

Bullet *patterns* (spiral, fan, and so on) are explicitly out of scope
per #28 -- "a shmup recipe on top" a game builds using `spawn()`, not
something this kit provides.
"""

from pyguara.kits.projectiles.projectile import Projectile
from pyguara.kits.projectiles.system import ProjectileSystem

__all__ = ["Projectile", "ProjectileSystem"]
