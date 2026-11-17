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

import math
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.component import StrictComponent
from pyguara.ecs.manager import EntityManager
from pyguara.native import require_extension

# Floats per agent in the row `_pack` writes; mirrors `STRIDE` in
# `rust/src/flocking.rs`, which rejects a length that is not a multiple.
_STRIDE = 15

# `tuple.__new__`, which is what `NamedTuple._make` calls, bound once
# rather than looked up per vector. See `FlockingSystem.update`.
_new_vector = tuple.__new__


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
    `.separation` and summing the weighted results, in one iteration over
    the neighbours.

    The arithmetic is on floats, not `Vector2`, on purpose: this loop runs
    once per neighbour per agent per tick. Distances are compared squared,
    so there is at most one `sqrt` per neighbour. `seek` is not included;
    it depends on a caller's target, not on the neighbourhood.

    Args:
        position: The steering agent's own world position.
        agent: The agent, read for its radii, weights and velocity.
        neighbors: `(position, velocity)` per flockmate, self excluded.

    Returns:
        The weighted sum of the three neighbourhood forces.
    """
    max_speed = agent.max_speed
    separation_radius = agent.separation_radius
    separation_radius_sq = separation_radius * separation_radius
    want_cohesion = agent.cohesion_weight != 0.0
    want_alignment = agent.alignment_weight != 0.0
    want_separation = agent.separation_weight != 0.0

    x, y = position.x, position.y
    count = 0
    sum_x = sum_y = 0.0
    sum_vx = sum_vy = 0.0
    push_x = push_y = 0.0

    for neighbor_position, neighbor_velocity in neighbors:
        count += 1
        neighbor_x, neighbor_y = neighbor_position.x, neighbor_position.y

        if want_cohesion:
            sum_x += neighbor_x
            sum_y += neighbor_y
        if want_alignment:
            sum_vx += neighbor_velocity.x
            sum_vy += neighbor_velocity.y
        if not want_separation:
            continue

        offset_x = x - neighbor_x
        offset_y = y - neighbor_y
        distance_sq = offset_x * offset_x + offset_y * offset_y
        if distance_sq >= separation_radius_sq:
            continue
        if distance_sq < 1e-06:
            # Coincident agents: push in a fixed, stable direction rather
            # than dividing by zero.
            push_x += max_speed
            continue
        distance = math.sqrt(distance_sq)
        # (1 - d/r) * max_speed, then divided by d to normalise the offset:
        # one multiply per axis instead of building a unit vector.
        scale = (1.0 - distance / separation_radius) * max_speed / distance
        push_x += offset_x * scale
        push_y += offset_y * scale

    if count == 0:
        return Vector2(0, 0)

    velocity_x, velocity_y = agent.velocity.x, agent.velocity.y
    force_x = force_y = 0.0
    inverse_count = 1.0 / count

    if want_cohesion:
        direction_x = sum_x * inverse_count - x
        direction_y = sum_y * inverse_count - y
        direction_sq = direction_x * direction_x + direction_y * direction_y
        if direction_sq >= 1e-06:
            scale = max_speed / math.sqrt(direction_sq)
            weight = agent.cohesion_weight
            force_x += (direction_x * scale - velocity_x) * weight
            force_y += (direction_y * scale - velocity_y) * weight

    if want_alignment:
        average_x = sum_vx * inverse_count
        average_y = sum_vy * inverse_count
        average_sq = average_x * average_x + average_y * average_y
        if average_sq > max_speed * max_speed:
            scale = max_speed / math.sqrt(average_sq)
            average_x *= scale
            average_y *= scale
        weight = agent.alignment_weight
        force_x += (average_x - velocity_x) * weight
        force_y += (average_y - velocity_y) * weight

    if want_separation:
        push_sq = push_x * push_x + push_y * push_y
        if push_sq > max_speed * max_speed:
            scale = max_speed / math.sqrt(push_sq)
            push_x *= scale
            push_y *= scale
        weight = agent.separation_weight
        force_x += push_x * weight
        force_y += push_y * weight

    return Vector2(force_x, force_y)


class FlockingSystem:
    """Ticks every `FlockingAgent` toward its neighbors, each frame.

    Neighbor query, weighted force sum, F=ma integration: the same
    integration shape as `SteeringSystem`.

    The flock is steered by the native extension, in one crossing per
    tick, and there is no Python implementation: `native_acceleration`
    and `PYGUARA_NO_NATIVE` do not apply. See ADR 0011, Decision 3.

    The sweep is Gauss-Seidel, so its order is part of the simulation. It
    follows entity insertion order, so a seeded flock ticks the same way
    every run.

    Example:
        >>> system_manager.register(FlockingSystem(entity_manager), priority=150)
    """

    def __init__(
        self,
        entity_manager: EntityManager,
        cell_size: float = 64.0,
        groups: int = 1,
        *,
        integrate: bool = True,
    ) -> None:
        """Initialize the flocking system.

        Args:
            entity_manager: The entity manager to query for flocking agents.
            cell_size: The neighbour grid's bucket size; pick something close to
                the typical `neighbor_radius`.
            groups: How many ticks to spread steering across. 1 (the
                default) steers every agent every tick. Higher values
                round-robin: each tick recomputes one group's steering
                while *every* agent still integrates its position, so
                motion stays smooth and only the decision rate drops.
                Values below 1 are clamped to 1.
            integrate: Whether to move each agent by its velocity. True, the
                default, writes `Transform.position` directly, which goes
                through walls. False only steers: each agent's `velocity` is
                updated and its position is left for something that collides
                to move, such as `TopDownSystem` or `CharacterMover`.

        Raises:
            RuntimeError: If the native extension cannot be imported.
        """
        self._entity_manager = entity_manager
        self._cell_size = cell_size
        self._integrate = integrate
        # Registered here, at system construction, which is what the API
        # asks for: the cache is maintained incrementally as components
        # come and go, so it only pays off for a query that runs every
        # frame. This one does.
        entity_manager.register_cached_query(FlockingAgent, Transform)
        self._groups = max(1, groups)
        self._tick = 0

        self._native: Any = require_extension("FlockingSystem").NativeFlockingSolver()

    def _pack(
        self, agents: list[FlockingAgent], transforms: list[Transform]
    ) -> list[float]:
        """Flatten the flock into one row of `_STRIDE` floats per agent.

        `seek_weight` is zeroed here when there is no target, so the native
        side's `!= 0.0` means exactly `agent.seek_weight and
        agent.seek_target is not None`.

        Args:
            agents: This tick's `FlockingAgent` components, by slot.
            transforms: This tick's `Transform` components, by slot.

        Returns:
            `len(agents) * _STRIDE` floats.
        """
        flat: list[float] = []
        extend = flat.extend
        for slot, agent in enumerate(agents):
            position = transforms[slot].position
            velocity = agent.velocity
            target = agent.seek_target
            if target is None or not agent.seek_weight:
                seek_weight = seek_x = seek_y = 0.0
            else:
                seek_weight, seek_x, seek_y = agent.seek_weight, target.x, target.y
            extend(
                (
                    position.x,
                    position.y,
                    velocity.x,
                    velocity.y,
                    agent.max_speed,
                    agent.max_force,
                    agent.mass,
                    agent.neighbor_radius,
                    agent.separation_radius,
                    agent.cohesion_weight,
                    agent.alignment_weight,
                    agent.separation_weight,
                    seek_weight,
                    seek_x,
                    seek_y,
                )
            )
        return flat

    def update(self, dt: float) -> None:
        """Update all flocking agents.

        Args:
            dt: Delta time in seconds.
        """
        entities = list(
            self._entity_manager.get_entities_with_cached(FlockingAgent, Transform)
        )
        if not entities:
            return

        # Resolve every component once, into parallel lists indexed by slot.
        # Everything downstream addresses a flockmate by slot, so the only
        # component lookups in a tick are these -- one per agent, rather
        # than two per *neighbour* per agent.
        agents = [entity.get_component(FlockingAgent) for entity in entities]
        transforms = [entity.get_component(Transform) for entity in entities]

        groups = self._groups
        steering_group = self._tick % groups
        self._tick += 1

        # One crossing for the whole flock. The write-back builds its
        # vectors with `_new_vector`, which is cheaper than `Vector2(x, y)`
        # and produces an identical object. A disabled agent is skipped,
        # not written back with the unchanged row the solver returns.
        enabled = [agent.enabled for agent in agents]
        rows = self._native.tick(
            dt,
            self._cell_size,
            groups,
            steering_group,
            self._pack(agents, transforms),
            enabled,
            self._integrate,
        )
        for (position, velocity), agent, transform, is_enabled in zip(
            rows, agents, transforms, enabled, strict=True
        ):
            if not is_enabled:
                continue
            if self._integrate:
                transform.position = _new_vector(Vector2, position)
            agent.velocity = _new_vector(Vector2, velocity)
