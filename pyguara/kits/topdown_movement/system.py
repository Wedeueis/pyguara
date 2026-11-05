"""System driving `TopDownBody`: solid collision plus actor separation.

Solid collide-and-slide reuses `CharacterMover` exactly as `PlatformerSystem`
does -- it is already generic, with no gravity assumption, so an arbitrary
(including 8-directional) velocity slides along walls the same way
platformer motion does. Actor-vs-actor separation is the genuinely new
mechanism `CharacterMover` doesn't provide: two actors closer than the sum
of their `separation_radius` are pushed directly apart, positionally,
rather than blocked like a solid.
"""

from __future__ import annotations

from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.kits.topdown_movement.body import TopDownBody
from pyguara.physics.bounds import collider_bounds
from pyguara.physics.character_mover import CharacterMover
from pyguara.physics.components import Collider
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.spatial.components import SpatialTracked

# Default half-extents for a character with no Collider -- matches the
# fallback PlatformerSystem uses for the same situation.
_DEFAULT_HALF_EXTENTS = Vector2(12.0, 12.0)

# A pair exactly on top of each other has no direction to separate along;
# push along an arbitrary fixed axis rather than divide by zero.
_DEGENERATE_PUSH_DIRECTION = Vector2(1.0, 0.0)


def step_body(
    mover: CharacterMover,
    entity_id: str,
    body: TopDownBody,
    transform: Transform,
    collider: Collider | None,
    delta_time: float,
) -> None:
    """Move one body by its velocity for one step, sliding along solids.

    This is everything a body's motion depends on apart from separation. A networked
    client replays it to predict its own character, so the host and the replay can't
    drift apart.

    Args:
        mover: Does the swept movement.
        entity_id: The body's entity, which its own collider must not block.
        body: Holds the velocity and the sub-pixel remainder.
        transform: Holds the position.
        collider: The entity's collider, or None to use the default box.
        delta_time: Length of the step in seconds.
    """
    # The collider's centre, not the entity's origin: `offset` moves the box the
    # mover sweeps, and is subtracted again on the way out.
    centre, half_extents = collider_bounds(transform, collider, _DEFAULT_HALF_EXTENTS)
    collider_offset = collider.offset if collider else Vector2(0.0, 0.0)
    result = mover.move(
        centre,
        half_extents,
        body.velocity * delta_time,
        body._remainder,
        entity_id,
    )
    transform.position = result.position - collider_offset
    body._remainder = result.remainder


class TopDownSystem:
    """Moves every `TopDownBody` and separates overlapping actors.

    Attributes:
        _entity_manager: EntityManager for querying entities.
        _mover: CharacterMover doing the actual swept movement.
        _spatial_index: Source of nearby-actor candidates for separation.
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        physics_engine: IPhysicsEngine,
        spatial_index: SpatialHash[str],
    ) -> None:
        """Store collaborators.

        Args:
            entity_manager: EntityManager to access entities and components.
            physics_engine: Physics engine for the mover's overlap queries.
            spatial_index: Broad-phase index `SpatialIndexSystem` keeps in
                sync; queried here to find separation candidates. An actor
                must carry `SpatialTracked` (as well as `TopDownBody`) to
                take part in separation, in either direction.
        """
        self._entity_manager = entity_manager
        self._mover = CharacterMover(physics_engine)
        self._spatial_index = spatial_index

    def update(self, delta_time: float) -> None:
        """Move every `TopDownBody`, then separate overlapping actors.

        Args:
            delta_time: Time elapsed since last update (seconds).
        """
        for entity in self._entity_manager.get_entities_with(TopDownBody, Transform):
            body = entity.get_component(TopDownBody)
            if body.moved_elsewhere:
                continue
            step_body(
                self._mover,
                entity.id,
                body,
                entity.get_component(Transform),
                (
                    entity.get_component(Collider)
                    if entity.has_component(Collider)
                    else None
                ),
                delta_time,
            )

        self._separate_actors()

    def _separate_actors(self) -> None:
        """Push every overlapping, separation-enabled actor pair apart.

        Each pair is resolved once: a candidate is skipped once its id
        stops sorting after the entity currently being processed, since
        that pair was already handled (or will be) from the other side.
        """
        for entity in self._entity_manager.get_entities_with(
            TopDownBody, Transform, SpatialTracked
        ):
            body = entity.get_component(TopDownBody)
            if body.separation_radius <= 0:
                continue
            transform = entity.get_component(Transform)

            # Sorted: the index answers in set order, which string hashing
            # changes per process, and each push moves what the next one
            # sees. Unsorted, a seeded game wouldn't repeat.
            for other_id in sorted(
                self._spatial_index.query_radius(
                    transform.world_position, body.separation_radius * 2
                )
            ):
                if other_id <= entity.id:
                    continue
                other = self._entity_manager.get_entity(other_id)
                if other is None or not other.has_component(TopDownBody):
                    continue
                other_body = other.get_component(TopDownBody)
                if other_body.separation_radius <= 0:
                    continue

                self._push_apart(
                    transform,
                    other.get_component(Transform),
                    body.separation_radius,
                    other_body.separation_radius,
                )

    @staticmethod
    def _push_apart(
        a: Transform, b: Transform, radius_a: float, radius_b: float
    ) -> None:
        """Move `a` and `b` apart by half their overlap each, if they overlap."""
        offset = b.position - a.position
        distance = offset.magnitude
        overlap = radius_a + radius_b - distance
        if overlap <= 0:
            return
        direction = (
            offset.normalize() if distance > 1e-6 else _DEGENERATE_PUSH_DIRECTION
        )
        a.position -= direction * (overlap / 2)
        b.position += direction * (overlap / 2)
