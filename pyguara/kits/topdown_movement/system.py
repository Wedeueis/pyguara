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
from pyguara.physics.character_mover import SKIN, CharacterMover
from pyguara.physics.components import Collider
from pyguara.physics.protocols import IPhysicsEngine
from pyguara.spatial.components import SpatialTracked

# Default half-extents for a character with no Collider -- matches the
# fallback PlatformerSystem uses for the same situation.
_DEFAULT_HALF_EXTENTS = Vector2(12.0, 12.0)

# A pair exactly on top of each other has no direction to separate along;
# push along an arbitrary fixed axis rather than divide by zero.
_DEGENERATE_PUSH_DIRECTION = Vector2(1.0, 0.0)

# The scalar types the native step computes exactly as Python would.
_PLAIN_NUMBERS = frozenset((float, int))


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
        # An engine that can step many bodies in one call says so by having
        # `step_bodies`, exactly as `sweep_box` is offered to the mover:
        # optional, free to decline any body, and never the reference.
        self._step_bodies = getattr(physics_engine, "step_bodies", None)

    def update(self, delta_time: float) -> None:
        """Move every `TopDownBody`, then separate overlapping actors.

        Args:
            delta_time: Time elapsed since last update (seconds).
        """
        moving: list[tuple[str, TopDownBody, Transform, Collider | None]] = []
        for entity in self._entity_manager.get_entities_with(TopDownBody, Transform):
            body = entity.get_component(TopDownBody)
            if body.moved_elsewhere:
                continue
            moving.append(
                (
                    entity.id,
                    body,
                    entity.get_component(Transform),
                    (
                        entity.get_component(Collider)
                        if entity.has_component(Collider)
                        else None
                    ),
                )
            )

        if self._step_bodies is not None and type(delta_time) is float:
            moving = self._step_batched(moving, delta_time)
        for entity_id, body, transform, collider in moving:
            step_body(self._mover, entity_id, body, transform, collider, delta_time)

        self._separate_actors()

    def _step_batched(
        self,
        moving: list[tuple[str, TopDownBody, Transform, Collider | None]],
        delta_time: float,
    ) -> list[tuple[str, TopDownBody, Transform, Collider | None]]:
        """Step what the engine can in one call; return what it could not.

        Exact, not approximate: each body the engine answers for ends where
        `step_body` would have put it, to the bit. The engine only answers
        while every solid is static, so no body's move depends on another's
        and the order they are stepped in cannot matter -- which is what
        lets the rest go through `step_body` afterwards.

        A body whose centre is not a pair of floats is left out: the
        ordinary path keeps an integer coordinate an integer, and a native
        double cannot. So is one whose velocity or remainder is anything
        but a plain `float` or `int` -- a NumPy scalar, say -- since the
        ordinary path computes in that type and the engine's `sweep_box`
        declines it for the same reason.

        Args:
            moving: `(entity_id, body, transform, collider)` per body to move.
            delta_time: Length of the step in seconds.

        Returns:
            The bodies still to be stepped, in their original order.
        """
        rows = []
        batched = []
        rest = []
        for entry in moving:
            entity_id, body, transform, collider = entry
            if collider is None:
                centre_x, centre_y = transform.position
                offset_x = offset_y = 0.0
                half_x, half_y = _DEFAULT_HALF_EXTENTS
            else:
                position = transform.position
                offset_x, offset_y = collider.offset
                centre_x = position[0] + offset_x
                centre_y = position[1] + offset_y
                half_x = collider.dimensions[0] / 2.0
                half_y = collider.dimensions[1] / 2.0
            velocity = body.velocity
            remainder = body._remainder
            if (
                type(centre_x) is not float
                or type(centre_y) is not float
                or type(velocity[0]) not in _PLAIN_NUMBERS
                or type(velocity[1]) not in _PLAIN_NUMBERS
                or type(remainder[0]) not in _PLAIN_NUMBERS
                or type(remainder[1]) not in _PLAIN_NUMBERS
            ):
                rest.append(entry)
                continue
            rows.append(
                (
                    centre_x,
                    centre_y,
                    offset_x,
                    offset_y,
                    half_x,
                    half_y,
                    velocity[0],
                    velocity[1],
                    remainder[0],
                    remainder[1],
                    entity_id,
                )
            )
            batched.append(entry)
        if not rows:
            return moving
        assert self._step_bodies is not None
        steps = self._step_bodies(rows, delta_time, SKIN)
        # A list and nothing else: None is the engine declining, and a test
        # double answers to any name with something that is not an answer.
        if type(steps) is not list or len(steps) != len(rows):
            return moving
        for entry, step in zip(batched, steps, strict=True):
            if step is None:
                rest.append(entry)
                continue
            x, y, remainder_x, remainder_y = step
            entry[2].position = Vector2(x, y)
            entry[1]._remainder = Vector2(remainder_x, remainder_y)
        return rest

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
