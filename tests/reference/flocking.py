"""The flocking system as plain Python, for the Rust solver to be held to.

One Gauss-Seidel sweep over the flock in entity order, on a Python
`SpatialHash`, with `flock_force` summing each agent's neighbours.
`FlockingSystem` does the same sweep in Rust. The two agree exactly on
neighbourhoods and on arithmetic with one flockmate, and to summation
noise on a real flock, because a neighbour sum has no fixed order here.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

from pyguara.ai.flocking_system import FlockingAgent, flock_force
from pyguara.ai.steering import SteeringBehavior
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from tests.reference.spatial import ReferenceSpatialHash


class ReferenceFlockingSystem:
    """Does what `FlockingSystem` does, one agent at a time in Python."""

    def __init__(
        self,
        entity_manager: EntityManager,
        cell_size: float = 64.0,
        groups: int = 1,
        *,
        integrate: bool = True,
    ) -> None:
        """Take the same arguments `FlockingSystem` takes."""
        self._entity_manager = entity_manager
        self._cell_size = cell_size
        self._integrate = integrate
        entity_manager.register_cached_query(FlockingAgent, Transform)
        self._groups = max(1, groups)
        self._tick = 0

    @staticmethod
    def _neighbors_of(
        index: int,
        position: Vector2,
        agent: FlockingAgent,
        spatial_hash: ReferenceSpatialHash[int],
        transforms: list[Transform],
        agents: list[FlockingAgent],
    ) -> Iterable[tuple[Vector2, Vector2]]:
        """Yield `(position, velocity)` for each flockmate in range.

        The hash is keyed on a slot in `transforms`/`agents`, not on an entity
        id, so resolving a neighbour is two list subscripts.

        Both reads are live, not snapshotted: the hash is built from
        start-of-tick positions, but an agent steering later in the tick sees
        the already-moved positions of the agents ahead of it. Snapshotting
        would change how a flock settles.

        Args:
            index: The steering agent's own slot, excluded from its neighbours.
            position: Its world position, the query centre.
            agent: Read for `neighbor_radius`.
            spatial_hash: This tick's index, keyed by slot.
            transforms: This tick's `Transform` components, by slot.
            agents: This tick's `FlockingAgent` components, by slot.

        Yields:
            One `(position, velocity)` pair per flockmate.
        """
        for slot in spatial_hash.query_radius(position, agent.neighbor_radius):
            if slot == index:
                continue
            # No None check: slots index lists built from this tick's live
            # entities, so unlike an id lookup they cannot miss.
            yield transforms[slot].position, agents[slot].velocity

    def update(self, dt: float) -> None:
        """Steer and move every enabled agent, in entity order."""
        entities = list(
            self._entity_manager.get_entities_with_cached(FlockingAgent, Transform)
        )
        if not entities:
            return

        agents = [entity.get_component(FlockingAgent) for entity in entities]
        transforms = [entity.get_component(Transform) for entity in entities]

        groups = self._groups
        steering_group = self._tick % groups
        self._tick += 1

        # The Python index: a reference with the Rust index inside it would
        # be comparing the Rust grid with itself.
        spatial_hash: ReferenceSpatialHash[int] = ReferenceSpatialHash(self._cell_size)
        for slot, transform in enumerate(transforms):
            spatial_hash.insert(slot, transform.position)

        # One group's worth of accumulated acceleration, so a staggered
        # agent turns at the same rate as an unstaggered one instead of
        # `groups` times slower.
        steering_dt = dt * groups

        for slot, agent in enumerate(agents):
            if not agent.enabled:
                continue
            transform = transforms[slot]

            if groups > 1 and slot % groups != steering_group:
                # Not this agent's tick to think. It still moves.
                if self._integrate:
                    transform.position = transform.position + agent.velocity * dt
                continue

            position = transform.position
            force = flock_force(
                position,
                agent,
                self._neighbors_of(
                    slot, position, agent, spatial_hash, transforms, agents
                ),
            )
            if agent.seek_weight and agent.seek_target is not None:
                force = (
                    force
                    + SteeringBehavior.seek(
                        transform, agent.seek_target, agent.max_speed, agent.velocity
                    )
                    * agent.seek_weight
                )

            if force.length > agent.max_force:
                force = cast(Vector2, force.normalized() * agent.max_force)

            acceleration = force * (1.0 / agent.mass)
            new_velocity = agent.velocity + acceleration * steering_dt
            if new_velocity.length > agent.max_speed:
                new_velocity = cast(
                    Vector2, new_velocity.normalized() * agent.max_speed
                )
            agent.velocity = new_velocity

            if self._integrate:
                transform.position = transform.position + agent.velocity * dt
