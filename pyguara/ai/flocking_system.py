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

        spatial_hash: SpatialHash[str] = SpatialHash(cell_size=self._cell_size)
        for entity in entities:
            spatial_hash.insert(entity.id, entity.get_component(Transform).position)

        for entity in entities:
            agent = entity.get_component(FlockingAgent)
            if not agent.enabled:
                continue
            transform = entity.get_component(Transform)

            neighbor_positions: list[Vector2] = []
            neighbor_velocities: list[Vector2] = []
            for neighbor_id in spatial_hash.query_radius(
                transform.position, agent.neighbor_radius
            ):
                if neighbor_id == entity.id:
                    continue
                neighbor = self._entity_manager.get_entity(neighbor_id)
                if neighbor is None:
                    continue
                neighbor_agent = neighbor.get_component(FlockingAgent)
                neighbor_positions.append(neighbor.get_component(Transform).position)
                neighbor_velocities.append(neighbor_agent.velocity)

            force = Vector2(0, 0)
            if agent.cohesion_weight:
                force = (
                    force
                    + SteeringBehavior.cohesion(
                        transform, neighbor_positions, agent.max_speed, agent.velocity
                    )
                    * agent.cohesion_weight
                )
            if agent.alignment_weight:
                force = (
                    force
                    + SteeringBehavior.alignment(
                        neighbor_velocities, agent.max_speed, agent.velocity
                    )
                    * agent.alignment_weight
                )
            if agent.separation_weight:
                force = (
                    force
                    + SteeringBehavior.separation(
                        transform,
                        neighbor_positions,
                        agent.separation_radius,
                        agent.max_speed,
                    )
                    * agent.separation_weight
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
