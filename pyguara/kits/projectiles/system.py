"""Moves pooled projectiles, checks hits against the spatial hash, and renders."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.pipeline.viewport import Viewport
from pyguara.graphics.protocols import IRenderer
from pyguara.graphics.types import RenderBatch
from pyguara.kits.action_combat import Health, Hurtbox, apply_damage
from pyguara.kits.projectiles.projectile import Projectile
from pyguara.kits.stats import DamageType, StatBlock
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.resources.types import Texture

HitHandler = Callable[[Projectile, Entity], bool]
"""What a hit does: given the projectile and the target, return whether the
projectile is spent. False means the target was passed -- a dodge -- and the
projectile flies on, never offering that target to the handler again."""


class ProjectileSystem:
    """A pool of projectiles: spawn, move, hit-check, render.

    Mirrors `ParticleSystem`'s shape (a pre-allocated ring-buffer pool,
    `spawn`/`update`/`render`, scene-composed rather than DI-registered).
    Collision is checked against the shared `SpatialHash` (#98) instead of
    physics -- cheap enough for the volume of projectiles a shmup-style
    bullet pattern produces, matching the spatial hash's own "shooter
    bullets" design rationale. A candidate must carry `Hurtbox`, `Health`
    and a `Transform` to be a valid target -- the index finds it, and its
    `Transform` says exactly where it is; `StatBlock` is read for mitigation if
    present, skipped otherwise.

    Each tick checks the whole step, not only where the projectile ends
    up, so a shot moving further than its own `hit_radius` in a tick still
    hits what it passes. Candidates are tried in the order the projectile
    reaches them, then by entity id -- never in the spatial index's own
    order, which is a set's for the Python store and differs between runs.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        dispatcher: EventDispatcher,
        spatial_index: SpatialHash[str],
        capacity: int = 256,
        *,
        on_hit: HitHandler | None = None,
        solids: IPhysicsEngine | None = None,
        solid_mask: int = 0xFFFFFFFF,
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
            on_hit: What a hit does. The default calls
                `kits.action_combat.apply_damage()` with the projectile's
                fields and spends the projectile; a game with its own damage
                rules (dodge, shields, its own events) passes a handler
                instead. See `HitHandler`. Team and `Hurtbox`/`Health`
                filtering happens before it is called either way.
            solids: Walls. When given, each step is raycast against it and a
                projectile stops at the first thing it meets, hitting only
                targets before that point. None (the default) lets
                projectiles fly through everything.
            solid_mask: Collision mask for that raycast.
        """
        self._on_hit: HitHandler = on_hit if on_hit is not None else self._damage
        self._solids = solids
        self._solid_mask = solid_mask
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
        payload: Any = None,
    ) -> Projectile | None:
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
            payload: See `Projectile.payload`.

        Returns:
            The projectile, or None if the pool was full and it was dropped.
            The pool reuses it once it expires or hits, so hold on to it only
            while it is active.
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
                projectile.passed.clear()
                projectile.payload = payload
                projectile.active = True
                return projectile

            self._next_index = (self._next_index + 1) % self._capacity
            if self._next_index == search_start:
                return None  # Pool full; drop the spawn, like ParticleSystem.

    def update(self, dt: float) -> None:
        """Advance every active projectile and resolve any hit."""
        for projectile in self._pool:
            if not projectile.active:
                continue
            projectile.life -= dt
            if projectile.life <= 0:
                projectile.active = False
                continue
            start = projectile.position
            end = start + projectile.velocity * dt
            blocked = False
            if self._solids is not None and end != start:
                wall = self._solids.raycast(start, end, self._solid_mask)
                if wall is not None:
                    end = wall.position
                    blocked = True
            if not self._check_hit(projectile, start, end) and blocked:
                projectile.active = False

    def _check_hit(self, projectile: Projectile, start: Vector2, end: Vector2) -> bool:
        """Offer each target along `start`-`end` to the handler, nearest first.

        The handler sees the projectile at the point where it reached the
        target, so an impact effect can be drawn there.

        Returns:
            Whether the projectile was spent, in which case it is also
            deactivated and left at that point. Otherwise it ends at `end`.
        """
        step = end - start
        step_sq = step.x * step.x + step.y * step.y
        reach_sq = projectile.hit_radius * projectile.hit_radius
        middle = (start + end) * 0.5
        query_radius = projectile.hit_radius + 0.5 * step_sq**0.5

        along: list[tuple[float, str, Entity]] = []
        for entity_id in self._spatial_index.query_radius(middle, query_radius):
            if entity_id in projectile.passed:
                continue
            entity = self._entity_manager.get_entity(entity_id)
            if entity is None:
                continue
            if not (
                entity.has_component(Hurtbox)
                and entity.has_component(Health)
                and entity.has_component(Transform)
            ):
                continue
            hurtbox = entity.get_component(Hurtbox)
            if (
                projectile.team is not None
                and hurtbox.team is not None
                and projectile.team == hurtbox.team
            ):
                continue
            offset = entity.get_component(Transform).world_position - start
            t = 0.0
            if step_sq > 0.0:
                t = (offset.x * step.x + offset.y * step.y) / step_sq
                t = min(1.0, max(0.0, t))
            closest_x = offset.x - step.x * t
            closest_y = offset.y - step.y * t
            if closest_x * closest_x + closest_y * closest_y > reach_sq:
                continue
            along.append((t, entity_id, entity))

        along.sort(key=lambda candidate: (candidate[0], candidate[1]))
        for t, entity_id, entity in along:
            projectile.position = start + step * t
            if self._on_hit(projectile, entity):
                projectile.active = False
                return True
            projectile.passed.add(entity_id)
        projectile.position = end
        return False

    def _damage(self, projectile: Projectile, entity: Entity) -> bool:
        """Apply the hit through `apply_damage()` and spend the projectile (the default)."""
        target_stats = (
            entity.get_component(StatBlock) if entity.has_component(StatBlock) else None
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
        return True

    def get_active(self) -> list[Projectile]:
        """Every currently active projectile.

        `render()` covers the common texture-batched case; a caller doing
        its own rendering (primitive shapes, no texture assets, a debug
        overlay) reads this list directly instead.
        """
        return [projectile for projectile in self._pool if projectile.active]

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
