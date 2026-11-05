"""#28's projectiles kit: pooled projectile entities on core spatial.

Not ECS entities, and not `Hitbox`/`TriggerVolume`-based -- `ProjectileSystem`
mirrors `ParticleSystem`'s plain-object pool and checks hits against the
shared spatial hash (#98) directly, matching that data structure's own
"shooter bullets" design rationale (cheap enough for the volume a
shmup-style bullet pattern produces; physics-body-per-bullet is not).
On a hit, calls `kits.action_combat.apply_damage()` the same way `Hitbox`
does, against any candidate carrying `Hurtbox`, `Health` and a `Transform`.

A game with damage rules of its own passes `on_hit=`, which decides what a
hit does and whether the projectile is spent; returning False is a dodge,
and the shot flies on past that target. `solids=` takes an
`IPhysicsEngine` holding the level's walls, and a shot stops at the first
one in its path. Each tick checks the whole step, nearest target first and
then by id, so a fast shot can't pass through a target between ticks and
the same seed always hits the same thing.

Bullet *patterns* (spiral, fan, and so on) are explicitly out of scope
per #28 -- "a shmup recipe on top" a game builds using `spawn()`, not
something this kit provides.
"""

from pyguara.kits.projectiles.projectile import Projectile
from pyguara.kits.projectiles.system import HitHandler, ProjectileSystem

__all__ = ["HitHandler", "Projectile", "ProjectileSystem"]
