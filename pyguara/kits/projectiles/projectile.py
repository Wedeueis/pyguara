"""One pooled projectile entry -- plain data, recycled by `ProjectileSystem`."""

from __future__ import annotations

from dataclasses import dataclass, field

from pyguara.common.types import Vector2
from pyguara.kits.stats.damage_type import DamageType
from pyguara.resources.types import Texture


@dataclass
class Projectile:
    """A single pooled projectile, mirroring `ParticleSystem`'s `Particle`.

    Not an ECS entity, and not `TriggerVolume`/`Hitbox`-based -- collision
    is `ProjectileSystem` querying the core spatial hash (#98) directly,
    the design the spatial hash's own "shooter bullets" use case was named
    for. This carries the same combat fields `Hitbox` does, since a hit
    calls the same `apply_damage()`.

    Attributes:
        position: Current world position.
        velocity: Movement vector per second.
        life: Seconds remaining before this projectile expires unhit.
        life_total: `life` at spawn time, for a subclass wanting to fade
            by remaining-life fraction (`FloatingText`'s convention);
            unused by the base render.
        texture: Visual representation. `None` particles are skipped by
            `render()`, never simulated as invisible.
        active: Whether this slot is currently in use.
        rotation: Sprite rotation in degrees.
        scale: Sprite scale.
        hit_radius: Query radius for the spatial-hash hit check each tick.
        team: See `kits.action_combat.Hitbox.team` -- same matching rule
            against a target's `Hurtbox.team`.
        damage: Base damage, before crit/mitigation.
        damage_type: See `kits.stats.DamageType`.
        is_critical: Forwarded to `apply_damage()`.
        pierce_fraction: Forwarded to `apply_damage()`.
        invincibility_duration: Forwarded to `apply_damage()`.
        attacker: Entity id to record as `DamageDealt.attacker`, if any.
    """

    position: Vector2 = field(default_factory=Vector2.zero)
    velocity: Vector2 = field(default_factory=Vector2.zero)
    life: float = 0.0
    life_total: float = 0.0
    texture: Texture | None = None
    active: bool = False

    rotation: float = 0.0
    scale: Vector2 = field(default_factory=lambda: Vector2(1, 1))

    hit_radius: float = 8.0
    team: str | None = None
    damage: float = 0.0
    damage_type: DamageType = DamageType.PHYSICAL
    is_critical: bool = False
    pierce_fraction: float = 0.0
    invincibility_duration: float = 0.0
    attacker: str | None = None
