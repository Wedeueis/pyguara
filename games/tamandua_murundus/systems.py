"""The clearing's rules: mounds feed, insects drift, the tongue lashes.

D1's swarm is deliberately small and hand-driven -- enough insects for the
tongue to have work and for the mounds to visibly matter. **D2 replaces
`InsectDriftSystem` with the pooled, flocked swarm**; the tongue and the
mounds are unchanged by that, which is why they are separated here.
"""

from __future__ import annotations

import math

from games.tamandua_murundus.components import Insect, Murundu, Tamandua
from games.tamandua_murundus.events import (
    InsectKilled,
    MurunduBroken,
    TongueLashed,
)
from games.tamandua_murundus.swarm import Swarm
from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.ecs.pool import Poolable
from pyguara.events.dispatcher import EventDispatcher

# The interactive cap now lives on the `Swarm` itself (`swarm.SWARM_CAP`),
# because the pool is what enforces it: `release_at()` returns None when
# every insect is already out, which is the cap doing its job rather than
# a count this module has to keep.


class MurunduSystem:
    """Ticks each mound's feed timer and releases insects from it."""

    def __init__(
        self,
        entity_manager: EntityManager,
        dispatcher: EventDispatcher,
        swarm: Swarm,
        *,
        release_per_feed: int = 1,
    ) -> None:
        """Store collaborators.

        Args:
            entity_manager: Source of mounds.
            dispatcher: Where `MurunduBroken` is dispatched.
            swarm: Where released insects come from. The pool enforces the
                cap, so this system never counts insects itself.
            release_per_feed: How many insects each feed releases. The run
                clock raises this as the night goes on (D3 onward); D2
                leaves it at one so the swarm builds at a readable rate.
        """
        self._entity_manager = entity_manager
        self._dispatcher = dispatcher
        self._swarm = swarm
        self.release_per_feed = release_per_feed

    def update(self, dt: float) -> None:
        """Advance every intact mound's feed timer."""
        for entity in self._entity_manager.get_entities_with(Murundu, Transform):
            mound = entity.get_component(Murundu)
            if mound.broken:
                continue

            mound.glow_phase += dt
            mound.feed_timer -= dt
            if mound.feed_timer > 0.0:
                continue

            mound.feed_timer = mound.feed_interval
            origin = entity.get_component(Transform).position
            for _ in range(self.release_per_feed):
                if self._swarm.release_at(origin, entity.id) is None:
                    # Pool exhausted. Stop asking this frame rather than
                    # spinning through the rest of the releases.
                    break

    def damage(self, entity_id: str, amount: float) -> bool:
        """Take `amount` off a mound, breaking it if it reaches zero.

        Args:
            entity_id: The mound's entity id.
            amount: Damage to apply.

        Returns:
            Whether this hit broke the mound.
        """
        entity = self._entity_manager.get_entity(entity_id)
        if entity is None or not entity.has_component(Murundu):
            return False

        mound = entity.get_component(Murundu)
        if mound.broken:
            return False

        mound.health = max(0.0, mound.health - amount)
        if mound.health > 0.0:
            return False

        mound.broken = True
        remaining = sum(
            1
            for other in self._entity_manager.get_entities_with(Murundu)
            if not other.get_component(Murundu).broken
        )
        self._dispatcher.dispatch(
            MurunduBroken(
                entity=entity_id,
                position=entity.get_component(Transform).position,
                remaining=remaining,
            )
        )
        return True


class TongueSystem:
    """Auto-lashes the nearest insect in the arc in front of the anteater.

    Target search goes through the shared `SpatialHash` rather than a scan
    over every insect: at D1's sixty that is indistinguishable, but D2
    raises the count by an order of magnitude and the tongue should not be
    the thing that stops scaling.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        dispatcher: EventDispatcher,
        spatial_index: SpatialHash[str],
        swarm: Swarm,
    ) -> None:
        """Store collaborators.

        Args:
            entity_manager: Source of anteaters and hit candidates.
            dispatcher: Where `TongueLashed` and `InsectKilled` go.
            spatial_index: Queried for candidates near the snout.
            swarm: A killed insect goes back to its pool rather than being
                destroyed -- at this rate of death, creating and removing
                entities is exactly the cost the pool exists to avoid.
        """
        self._entity_manager = entity_manager
        self._dispatcher = dispatcher
        self._spatial_index = spatial_index
        self._swarm = swarm

    def update(self, dt: float) -> None:
        """Tick every anteater's cooldown and lash when it is ready."""
        for entity in self._entity_manager.get_entities_with(Tamandua, Transform):
            hunter = entity.get_component(Tamandua)
            hunter.tongue_cooldown = max(0.0, hunter.tongue_cooldown - dt)
            if hunter.tongue_cooldown > 0.0:
                continue

            origin = entity.get_component(Transform).position
            target = self._nearest_in_arc(origin, hunter)
            if target is None:
                continue

            hunter.tongue_cooldown = hunter.tongue_interval
            target_position = target.get_component(Transform).position
            insect = target.get_component(Insect)
            insect.health -= 1.0

            if insect.health <= 0.0:
                self._swarm.kill(target)
                self._dispatcher.dispatch(
                    InsectKilled(entity=target.id, position=target_position)
                )

            self._dispatcher.dispatch(
                TongueLashed(origin=origin, target=target_position, hit=True)
            )

    def _nearest_in_arc(self, origin: Vector2, hunter: Tamandua):
        """Return the closest insect inside the tongue's wedge, or None."""
        forward = Vector2(math.cos(hunter.facing), math.sin(hunter.facing))
        cos_half = math.cos(hunter.tongue_arc / 2.0)

        best = None
        best_distance = float("inf")
        for candidate_id in self._spatial_index.query_radius(
            origin, hunter.tongue_range
        ):
            candidate = self._entity_manager.get_entity(candidate_id)
            if candidate is None or not candidate.has_component(Insect):
                continue
            # A pooled insect that is not currently out is still an entity
            # and still in the spatial index; without this the tongue eats
            # the dead, from wherever they were last released.
            if not candidate.get_component(Poolable).is_active:
                continue

            offset = candidate.get_component(Transform).position - origin
            distance = offset.magnitude
            if distance <= 0.0:
                return candidate
            if offset.x * forward.x + offset.y * forward.y < cos_half * distance:
                continue
            if distance < best_distance:
                best, best_distance = candidate, distance

        return best
