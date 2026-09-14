"""XP motes: what a dead insect leaves behind, and who comes to get it.

A pooled layer with the same discipline `swarm.py` arrived at the hard
way: **the query-visible components go on at acquire and come off at
release.** `EntityPool` never destroys anything, so an `Attracted` or a
`SpatialTracked` attached at construction would keep every mote in
`MagnetSystem`'s candidate set and in the spatial index for the life of
the scene, whether one is on the ground or two hundred. That cost the
swarm two thirds of its frame rate in D2; it would cost the same here.

The magnet itself is `kits/progression`'s, and is deliberately **not a
physics interaction** -- a radius query and a velocity, no collider. A
mote passes through a murundu on its way to the anteater, which is what
the genre wants and what keeps a few hundred of them affordable.
"""

from __future__ import annotations

import math

from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.types import Color, Rect, Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.pool import EntityPool, Poolable
from pyguara.graphics.types import RenderBatch
from pyguara.kits.progression import Attracted
from pyguara.resources.types import Texture
from pyguara.spatial.components import SpatialTracked

# How many motes can be on the ground at once. Well under `SWARM_CAP`:
# the anteater's magnet keeps up with its own kill rate, so a backlog
# this size only builds if the player stops collecting entirely -- and a
# clearing carpeted in uncollected experience reads as a bug rather than
# as generosity.
MOTE_CAP = 220

# Experience per mote. A flat value, not a table: what a kill is *worth*
# is one number, and making it vary would be balance dressed up as depth.
MOTE_VALUE = 1.0

# Motes are the same bioluminescent green as a lit insect, because that is
# what they are -- what is left of one. Drawn brighter than the swarm so a
# dropped mote reads against the crowd it came out of.
MOTE_TINT = Color(168, 255, 214)

# How far a mote scatters from the kill, and how quickly it settles.
SCATTER = 26.0
SETTLE_DRAG = 5.0


class Motes:
    """The pooled XP motes on the clearing floor."""

    def __init__(
        self,
        entity_manager: EntityManager,
        arena: Rect,
        rng: RandomStream,
        *,
        cap: int = MOTE_CAP,
    ) -> None:
        """Pre-allocate the pool.

        Args:
            entity_manager: Where the motes live.
            arena: Keeps a scattered mote inside the clearing.
            rng: Drives the scatter direction.
            cap: How many motes can be on the ground at once.
        """
        self._entity_manager = entity_manager
        self._arena = arena
        self._rng = rng
        self._drift: dict[str, Vector2] = {}
        self._pool = EntityPool(entity_manager, "motes", cap, self._make_mote)

    def _make_mote(self, entity_manager: EntityManager, index: int) -> Entity:
        """Build one pooled mote, carrying only what an idle one needs.

        `Attracted` and `SpatialTracked` are attached on acquire -- see
        the module docstring for why that is not a detail.
        """
        entity = entity_manager.create_entity()
        entity.add_component(Poolable())
        entity.add_component(Transform(position=Vector2.zero()))
        return entity

    @property
    def active_count(self) -> int:
        """How many motes are on the ground."""
        return self._pool.active_count

    def drop(self, position: Vector2, value: float = MOTE_VALUE) -> Entity | None:
        """Leave a mote where an insect died.

        Scattered a little rather than dropped on the spot, so a cluster
        of kills leaves a spread of motes instead of a stack the player
        cannot tell the size of.

        Returns:
            The mote, or None if the pool is exhausted -- the cap doing
            its job, not an error.
        """
        entity = self._pool.acquire()
        if entity is None:
            return None

        angle = self._rng.uniform(0.0, math.tau)
        distance = self._rng.uniform(0.0, SCATTER)
        arena = self._arena
        entity.get_component(Transform).position = Vector2(
            min(max(position.x + math.cos(angle) * distance, arena.left), arena.right),
            min(max(position.y + math.sin(angle) * distance, arena.top), arena.bottom),
        )

        entity.add_component(Attracted(payload=value))
        entity.add_component(SpatialTracked())
        self._drift[entity.id] = Vector2(
            math.cos(angle) * distance * 1.6, math.sin(angle) * distance * 1.6
        )
        return entity

    def collect(self, entity_id: str) -> None:
        """Take a collected mote back into the pool.

        A no-op for anything that is not a live mote, so the scene can
        hand this every `PickupCollected` it sees without first working
        out whether the pickup was one of ours.
        """
        entity = self._entity_manager.get_entity(entity_id)
        if entity is None or not entity.has_component(Attracted):
            return

        entity.remove_component(Attracted)
        entity.remove_component(SpatialTracked)
        self._drift.pop(entity_id, None)
        self._pool.release(entity)

    def update(self, dt: float) -> None:
        """Let each mote's scatter settle.

        Only the scatter: once a magnet has hold of a mote, `MagnetSystem`
        owns its position, and a second mover would fight it for the same
        `Transform`. The drift is damped to nothing within a few frames,
        so in practice the two never overlap for long.
        """
        if not self._drift:
            return

        decay = max(0.0, 1.0 - SETTLE_DRAG * dt)
        arena = self._arena
        for entity in self._pool.get_active():
            drift = self._drift.get(entity.id)
            if drift is None:
                continue

            transform = entity.get_component(Transform)
            transform.position = Vector2(
                min(max(transform.position.x + drift.x * dt, arena.left), arena.right),
                min(max(transform.position.y + drift.y * dt, arena.top), arena.bottom),
            )
            self._drift[entity.id] = Vector2(drift.x * decay, drift.y * decay)

    def build_batch(self, texture: Texture, glow: float) -> RenderBatch:
        """One instanced, tinted batch for every mote on the ground.

        Pure in the same sense `swarm.build_batch()` is -- it reads the
        pool and nothing else -- so what the motes look like is testable
        without a GPU, which matters because this demo cannot boot
        headlessly at all.

        Args:
            texture: The shared insect texture; a mote is a brighter one.
            glow: 0..1, so motes dim with the clearing rather than sitting
                at full brightness through a bright dusk.
        """
        destinations = [
            (
                entity.get_component(Transform).position.x,
                entity.get_component(Transform).position.y,
            )
            for entity in self._pool.get_active()
        ]
        alpha = int(170 + 85 * max(0.0, min(1.0, glow)))
        return RenderBatch(
            texture=texture,
            destinations=destinations,
            rotations=[0.0] * len(destinations),
            scales=[(1.1, 1.1)] * len(destinations),
            transforms_enabled=True,
            colors=[(MOTE_TINT.r, MOTE_TINT.g, MOTE_TINT.b, alpha)] * len(destinations),
            colors_enabled=True,
        )
