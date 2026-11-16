"""The projectiles kit: pooled projectiles checked against the spatial hash.

Projectiles are plain pooled objects, not ECS entities. Each tick,
`ProjectileSystem` checks a shot's whole step against the shared
`SpatialHash`, nearest target first and then by id. A shot reaches a
target at its edge: its `hit_radius` plus the target's
`Hurtbox.radius`. A hit calls `kits.action_combat.apply_damage()`
unless `on_hit=` replaces it. `solids=` stops a shot at the first
wall in its path, and `on_end=` is told why each projectile stopped.
"""

from pyguara.kits.projectiles.projectile import Projectile
from pyguara.kits.projectiles.system import (
    EndHandler,
    HitHandler,
    ProjectileEnd,
    ProjectileSystem,
)

__all__ = [
    "EndHandler",
    "HitHandler",
    "Projectile",
    "ProjectileEnd",
    "ProjectileSystem",
]
