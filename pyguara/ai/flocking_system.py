"""System for boid flocking: cohesion, alignment, separation, and seek.

Sums cohesion, alignment, separation, and an optional seek target into one
steering force per agent, each tick.

Kept as a sibling of `SteeringSystem` rather than a new dispatch branch on
it: a flock needs neighbor queries and a *sum* of forces every tick, while
`SteeringSystem` is a closed dispatch over exactly one behavior per entity.
An entity can carry both components (e.g. the jaguar uses plain
`SteeringAgent` flee/evade while the pack uses `FlockingAgent`).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import cast

from pyguara.ai.steering import SteeringBehavior
from pyguara.common.components import Transform
from pyguara.common.spatial import SpatialHash
from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent
from pyguara.ecs.manager import EntityManager


@dataclass(slots=True)
class FlockingAgent(StrictComponent):
    """Per-entity boid tuning and runtime velocity.

    Attributes:
        max_speed: Maximum movement speed.
        max_force: Maximum steering force (turn speed/acceleration).
        mass: Used to calculate acceleration (Force / Mass).
        velocity: Current velocity of the agent.
        neighbor_radius: Distance within which other `FlockingAgent`s count
            as flockmates for cohesion/alignment.
        separation_radius: Distance within which flockmates push apart.
            Usually smaller than `neighbor_radius`.
        cohesion_weight: Blend weight for steering toward the flock center.
        alignment_weight: Blend weight for matching the flock's heading.
        separation_weight: Blend weight for pushing apart from close
            flockmates. Kept high relative to the others by default -- a
            weak separation relative to cohesion/seek is what produces
            visible jitter as agents fight over the same space.
        seek_weight: Blend weight for `seek_target`, e.g. a flow-field
            direction or an assigned flanking vector. Zero if unused.
        seek_target: Optional external steering target (world position);
            ignored when `seek_weight` is zero.
        enabled: Whether this agent should be updated at all.
    """

    max_speed: float = 150.0
    max_force: float = 400.0
    mass: float = 1.0
    velocity: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    neighbor_radius: float = 80.0
    separation_radius: float = 30.0
    cohesion_weight: float = 1.0
    alignment_weight: float = 1.0
    separation_weight: float = 1.5
    seek_weight: float = 1.0
    seek_target: Vector2 | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a
        zero-argument `super()` still resolves against the discarded
        original, raising TypeError on every instantiation.
        """
        StrictComponent.__init__(self)


def flock_force(
    position: Vector2,
    agent: FlockingAgent,
    neighbors: Iterable[tuple[Vector2, Vector2]],
) -> Vector2:
    """Sum cohesion, alignment and separation in a single pass.

    Equivalent to calling `SteeringBehavior.cohesion`, `.alignment` and
    `.separation` and summing the weighted results -- `test_ai_flocking.py`
    asserts that equivalence directly, because it is the whole safety net
    for this function existing at all.

    It exists because the three behaviours each want a different reduction
    over the *same* neighbour list: cohesion needs the mean position,
    alignment the mean velocity, separation a distance-weighted push. Run
    separately that is three iterations plus two `sum(..., Vector2(0, 0))`
    allocations, on top of the pass that collected the neighbours. Fused,
    it is one.

    `seek` is deliberately not folded in: it takes a caller-supplied
    target rather than anything about the neighbourhood, so it costs one
    call per agent regardless and reads better left where it is.

    Args:
        position: The steering agent's own world position.
        agent: The agent, read for its radii, weights and velocity.
        neighbors: `(position, velocity)` per flockmate, self excluded.

    Returns:
        The weighted sum of the three neighbourhood forces.
    """
    max_speed = agent.max_speed
    separation_radius = agent.separation_radius
    want_cohesion = agent.cohesion_weight != 0.0
    want_alignment = agent.alignment_weight != 0.0
    want_separation = agent.separation_weight != 0.0

    count = 0
    position_sum = Vector2(0, 0)
    velocity_sum = Vector2(0, 0)
    separation_push = Vector2(0, 0)

    for neighbor_position, neighbor_velocity in neighbors:
        count += 1
        if want_cohesion:
            position_sum = position_sum + neighbor_position
        if want_alignment:
            velocity_sum = velocity_sum + neighbor_velocity
        if not want_separation:
            continue

        offset = position - neighbor_position
        distance = offset.length
        if distance >= separation_radius:
            continue
        if distance < 0.001:
            # Coincident agents: push in a fixed, stable direction rather
            # than dividing by zero.
            separation_push = separation_push + Vector2(1, 0) * max_speed
            continue
        weight = 1.0 - (distance / separation_radius)
        separation_push = separation_push + cast(
            Vector2, offset.normalized() * (weight * max_speed)
        )

    if count == 0:
        return Vector2(0, 0)

    force = Vector2(0, 0)
    inverse_count = 1.0 / count

    if want_cohesion:
        centre = position_sum * inverse_count
        direction = centre - position
        if direction.length >= 0.001:
            desired = cast(Vector2, direction.normalized() * max_speed)
            force = force + (desired - agent.velocity) * agent.cohesion_weight

    if want_alignment:
        average = velocity_sum * inverse_count
        if average.length > max_speed:
            average = cast(Vector2, average.normalized() * max_speed)
        force = force + (average - agent.velocity) * agent.alignment_weight

    if want_separation:
        if separation_push.length > max_speed:
            separation_push = cast(Vector2, separation_push.normalized() * max_speed)
        force = force + separation_push * agent.separation_weight

    return force


class FlockingSystem:
    """Ticks every `FlockingAgent` toward its neighbors, each frame.

    Neighbor query, weighted force sum, F=ma integration -- the same
    integration shape as `SteeringSystem`.

    A fresh `SpatialHash` is built every `update()` from the entities'
    current positions rather than incrementally maintained: this system
    already visits every `FlockingAgent` each tick regardless, so a full
    rebuild costs nothing extra and, unlike an incrementally-maintained
    hash, can never accumulate a stale entry for a despawned entity.

    Example:
        >>> system_manager.register(FlockingSystem(entity_manager), priority=150)
    """

    def __init__(self, entity_manager: EntityManager, cell_size: float = 64.0) -> None:
        """Initialize the flocking system.

        Args:
            entity_manager: The entity manager to query for flocking agents.
            cell_size: `SpatialHash` bucket size; pick something close to
                the typical `neighbor_radius`.
        """
        self._entity_manager = entity_manager
        self._cell_size = cell_size

    @staticmethod
    def _neighbors_of(
        index: int,
        position: Vector2,
        agent: FlockingAgent,
        spatial_hash: SpatialHash[int],
        transforms: list[Transform],
        agents: list[FlockingAgent],
    ) -> Iterable[tuple[Vector2, Vector2]]:
        """Yield `(position, velocity)` for each flockmate in range.

        A generator, so the neighbourhood is never materialised as two
        lists that each get iterated again downstream -- which is the
        allocation `flock_force` exists to avoid.

        The hash is keyed on a position in `transforms`/`agents`, not on an
        entity id, so resolving a neighbour is two list subscripts instead
        of a manager lookup plus two component lookups. That is the single
        largest cost in a flocking tick at scale.

        Both reads are deliberately *live* rather than snapshotted. The
        pre-existing behaviour is Gauss-Seidel: the hash is built from
        start-of-tick positions, but an agent steering later in the tick
        sees the already-moved positions of the agents ahead of it.
        Snapshotting into flat float arrays would quietly convert that to
        Jacobi and change how a flock settles, which is not a change a
        performance commit should be making.

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
        """Update all flocking agents.

        Args:
            dt: Delta time in seconds.
        """
        entities = list(
            self._entity_manager.get_entities_with(FlockingAgent, Transform)
        )
        if not entities:
            return

        # Resolve every component once, into parallel lists indexed by slot.
        # Everything downstream addresses a flockmate by slot, so the only
        # component lookups in a tick are these -- one per agent, rather
        # than two per *neighbour* per agent.
        agents = [entity.get_component(FlockingAgent) for entity in entities]
        transforms = [entity.get_component(Transform) for entity in entities]

        spatial_hash: SpatialHash[int] = SpatialHash(cell_size=self._cell_size)
        for slot, transform in enumerate(transforms):
            spatial_hash.insert(slot, transform.position)

        for slot, agent in enumerate(agents):
            if not agent.enabled:
                continue
            transform = transforms[slot]

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
            new_velocity = agent.velocity + acceleration * dt
            if new_velocity.length > agent.max_speed:
                new_velocity = cast(
                    Vector2, new_velocity.normalized() * agent.max_speed
                )
            agent.velocity = new_velocity

            transform.position = transform.position + agent.velocity * dt
