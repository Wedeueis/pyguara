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
from pyguara.common.components import Transform
from pyguara.common.random import RandomStream
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Rect, Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher

# How many interactive insects D1 keeps alive at once. Small on purpose:
# this PR proves the tongue and the mounds, and a crowd here would make
# the D2 measurement look like a regression rather than a result.
D1_INSECT_CAP = 60


class MurunduSystem:
    """Ticks each mound's feed timer and releases insects from it."""

    def __init__(
        self,
        entity_manager: EntityManager,
        dispatcher: EventDispatcher,
        arena: Rect,
        rng: RandomStream,
    ) -> None:
        """Store collaborators.

        Args:
            entity_manager: Source of mounds, and where insects are made.
            dispatcher: Where `MurunduBroken` is dispatched.
            arena: Keeps released insects inside the clearing.
            rng: Drives release direction and wobble.
        """
        self._entity_manager = entity_manager
        self._dispatcher = dispatcher
        self._arena = arena
        self._rng = rng

    def update(self, dt: float) -> None:
        """Advance every intact mound's feed timer."""
        insects = sum(1 for _ in self._entity_manager.get_entities_with(Insect))

        for entity in self._entity_manager.get_entities_with(Murundu, Transform):
            mound = entity.get_component(Murundu)
            if mound.broken:
                continue

            mound.glow_phase += dt
            mound.feed_timer -= dt
            if mound.feed_timer > 0.0 or insects >= D1_INSECT_CAP:
                continue

            mound.feed_timer = mound.feed_interval
            self._release(entity.get_component(Transform).position, entity.id)
            insects += 1

    def _release(self, origin: Vector2, anchor: str) -> None:
        """Put one insect into the world beside its mound."""
        angle = self._rng.uniform(0.0, math.tau)
        entity = self._entity_manager.create_entity()
        entity.add_component(
            Transform(
                position=Vector2(
                    origin.x + math.cos(angle) * 38.0,
                    origin.y + math.sin(angle) * 38.0,
                )
            )
        )
        entity.add_component(
            Insect(
                velocity=Vector2(math.cos(angle) * 42.0, math.sin(angle) * 42.0),
                wobble=self._rng.uniform(0.0, math.tau),
                anchor=anchor,
            )
        )

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


class InsectDriftSystem:
    """Moves D1's insects: outward from their mound, with a wobble.

    Placeholder motion, and labelled as such. The real behaviour is
    `FlockingSystem` in D2; what this has to do is keep insects on screen
    and moving differently from each other, so the tongue has a moving
    target and the clearing is not static.
    """

    def __init__(self, entity_manager: EntityManager, arena: Rect) -> None:
        """Store collaborators."""
        self._entity_manager = entity_manager
        self._arena = arena

    def update(self, dt: float) -> None:
        """Drift every insect, turning it back at the clearing's edge."""
        for entity in self._entity_manager.get_entities_with(Insect, Transform):
            insect = entity.get_component(Insect)
            transform = entity.get_component(Transform)

            insect.wobble += dt * 2.4
            drift = math.sin(insect.wobble) * 26.0
            heading = insect.velocity
            side = Vector2(-heading.y, heading.x)
            magnitude = side.magnitude
            if magnitude > 0.0:
                side = Vector2(side.x / magnitude, side.y / magnitude)

            position = Vector2(
                transform.position.x + (heading.x + side.x * drift) * dt,
                transform.position.y + (heading.y + side.y * drift) * dt,
            )

            # Turn back at the edge rather than clamping: a clamped insect
            # piles up against the boundary and the clearing grows a rim
            # of stuck sprites.
            if position.x < self._arena.left or position.x > self._arena.right:
                insect.velocity = Vector2(-insect.velocity.x, insect.velocity.y)
                position = Vector2(transform.position.x, position.y)
            if position.y < self._arena.top or position.y > self._arena.bottom:
                insect.velocity = Vector2(insect.velocity.x, -insect.velocity.y)
                position = Vector2(position.x, transform.position.y)

            transform.position = position


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
    ) -> None:
        """Store collaborators."""
        self._entity_manager = entity_manager
        self._dispatcher = dispatcher
        self._spatial_index = spatial_index

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

            killed = insect.health <= 0.0
            if killed:
                self._entity_manager.remove_entity(target.id)
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

            offset = candidate.get_component(Transform).position - origin
            distance = offset.magnitude
            if distance <= 0.0:
                return candidate
            if offset.x * forward.x + offset.y * forward.y < cos_half * distance:
                continue
            if distance < best_distance:
                best, best_distance = candidate, distance

        return best
