"""Moves pooled projectiles, checks hits against the spatial hash, and renders."""

from __future__ import annotations

from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.protocols import IRenderer
from pyguara.graphics.types import RenderBatch
from pyguara.kits.action_combat import Health, Hurtbox, apply_damage
from pyguara.kits.projectiles.projectile import Projectile
from pyguara.kits.stats import DamageType, StatBlock
from pyguara.resources.types import Texture


class ProjectileSystem:
    """A pool of projectiles: spawn, move, hit-check, render.

    Mirrors `ParticleSystem`'s shape (a pre-allocated ring-buffer pool,
    `spawn`/`update`/`render`, scene-composed rather than DI-registered).
    Collision is checked against the shared `SpatialHash` (#98) instead of
    physics -- cheap enough for the volume of projectiles a shmup-style
    bullet pattern produces, matching the spatial hash's own "shooter
    bullets" design rationale. A candidate must carry `Hurtbox` and
    `Health` to be a valid target; `StatBlock` is read for mitigation if
    present, skipped otherwise.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        dispatcher: EventDispatcher,
        spatial_index: SpatialHash[str],
        capacity: int = 256,
    ) -> None:
        """Pre-allocate the pool and store collaborators.

        Args:
            entity_manager: Source of hit-candidate entities, by id, from
                `spatial_index`'s query results.
            dispatcher: Where `apply_damage()` dispatches `DamageDealt`.
            spatial_index: Queried each tick for candidates near an active
                projectile. Entities are expected to already be tracked in
                it the normal way (`pyguara.spatial.SpatialTracked` +
                `SpatialIndexSystem`) -- this system never inserts into it
                itself.
            capacity: Maximum concurrent projectiles. `spawn()` beyond this
                silently drops, the same as `ParticleSystem`.
        """
        self._entity_manager = entity_manager
        self._dispatcher = dispatcher
        self._spatial_index = spatial_index
        self._pool = [Projectile() for _ in range(capacity)]
        self._capacity = capacity
        self._next_index = 0

    def spawn(
        self,
        texture: Texture | None,
        position: Vector2,
        velocity: Vector2,
        damage: float = 0.0,
        damage_type: DamageType = DamageType.PHYSICAL,
        life: float = 2.0,
        hit_radius: float = 8.0,
        team: str | None = None,
        is_critical: bool = False,
        pierce_fraction: float = 0.0,
        invincibility_duration: float = 0.0,
        attacker: str | None = None,
        rotation: float = 0.0,
        scale: Vector2 = Vector2(1, 1),
    ) -> None:
        """Spawn one projectile into the first free pool slot.

        Args:
            texture: Visual representation. `None` renders nothing but
                still moves and hits normally.
            position: World-space spawn point.
            velocity: World-space velocity, pixels/second.
            damage: Base damage, before crit/mitigation.
            damage_type: See `kits.stats.DamageType`.
            life: Seconds until this projectile expires unhit.
            hit_radius: Spatial-hash query radius for the hit check.
            team: See `Projectile.team`.
            is_critical: Forwarded to `apply_damage()`.
            pierce_fraction: Forwarded to `apply_damage()`.
            invincibility_duration: Forwarded to `apply_damage()`.
            attacker: Entity id to record as `DamageDealt.attacker`.
            rotation: Initial sprite rotation, degrees.
            scale: Sprite scale.
        """
        search_start = self._next_index
        while True:
            projectile = self._pool[self._next_index]
            if not projectile.active:
                projectile.position = position
                projectile.velocity = velocity
                projectile.life = life
                projectile.life_total = life
                projectile.texture = texture
                projectile.rotation = rotation
                projectile.scale = scale
                projectile.hit_radius = hit_radius
                projectile.team = team
                projectile.damage = damage
                projectile.damage_type = damage_type
                projectile.is_critical = is_critical
                projectile.pierce_fraction = pierce_fraction
                projectile.invincibility_duration = invincibility_duration
                projectile.attacker = attacker
                projectile.active = True
                return

            self._next_index = (self._next_index + 1) % self._capacity
            if self._next_index == search_start:
                return  # Pool full; drop the spawn, like ParticleSystem does.

    def update(self, dt: float) -> None:
        """Advance every active projectile and resolve any hit."""
        for projectile in self._pool:
            if not projectile.active:
                continue
            projectile.life -= dt
            if projectile.life <= 0:
                projectile.active = False
                continue
            projectile.position = projectile.position + projectile.velocity * dt
            self._check_hit(projectile)

    def _check_hit(self, projectile: Projectile) -> None:
        """Deactivate and apply damage on the first valid target found."""
        for entity_id in self._spatial_index.query_radius(
            projectile.position, projectile.hit_radius
        ):
            entity = self._entity_manager.get_entity(entity_id)
            if entity is None:
                continue
            if not entity.has_component(Hurtbox) or not entity.has_component(Health):
                continue
            hurtbox = entity.get_component(Hurtbox)
            if (
                projectile.team is not None
                and hurtbox.team is not None
                and projectile.team == hurtbox.team
            ):
                continue

            target_stats = (
                entity.get_component(StatBlock)
                if entity.has_component(StatBlock)
                else None
            )
            apply_damage(
                self._dispatcher,
                entity.id,
                entity.get_component(Health),
                projectile.damage,
                projectile.damage_type,
                target_stats=target_stats,
                pierce_fraction=projectile.pierce_fraction,
                is_critical=projectile.is_critical,
                invincibility_duration=projectile.invincibility_duration,
                attacker=projectile.attacker,
            )
            projectile.active = False
            return

    def render(
        self, backend: IRenderer, camera: Camera2D, viewport: Viewport | None = None
    ) -> None:
        """Draw every active, textured projectile, batched by texture."""
        if viewport is None:
            viewport = Viewport(0, 0, backend.width, backend.height)

        batches: dict[Texture, list[tuple[float, float]]] = {}
        zoom = camera.zoom
        offset = camera.screen_offset(viewport)

        for projectile in self._pool:
            if not projectile.active or projectile.texture is None:
                continue
            batches.setdefault(projectile.texture, []).append(
                (
                    projectile.position.x * zoom + offset.x,
                    projectile.position.y * zoom + offset.y,
                )
            )

        for texture, destinations in batches.items():
            backend.render_batch(RenderBatch(texture, destinations))
