"""System for updating steering behaviors."""

from typing import cast

from pyguara.ai.components import Navigator, SteeringAgent, SteeringBehaviorType
from pyguara.ai.steering import SteeringBehavior
from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.entity import Entity
from pyguara.ecs.manager import EntityManager

# Distance (world units) within which an ARRIVE agent is snapped to rest.
_ARRIVE_STOP_DISTANCE = 1.0


class SteeringSystem:
    """Updates steering agents and applies movement forces.

    Processes entities with SteeringAgent and Transform components,
    calculating and applying steering forces each frame.

    Compatible with SystemManager's update(dt) signature.

    Example:
        >>> system_manager.register(SteeringSystem(entity_manager), priority=150)
    """

    def __init__(self, entity_manager: EntityManager) -> None:
        """Initialize the steering system.

        Args:
            entity_manager: The entity manager to query for steering agents.
        """
        self._entity_manager = entity_manager
        # Store wander targets for persistence across frames
        self._wander_targets: dict[str, Vector2] = {}

    def update(self, dt: float) -> None:
        """Update all steering agents.

        Args:
            dt: Delta time in seconds.
        """
        for entity in self._entity_manager.get_entities_with(SteeringAgent, Transform):
            agent = entity.get_component(SteeringAgent)
            transform = entity.get_component(Transform)

            if not agent.enabled:
                continue

            # Determine target position
            target = self._get_target(entity, agent)
            if target is None and agent.behavior != SteeringBehaviorType.WANDER:
                continue

            # Calculate steering force based on behavior
            steering_force = self._calculate_steering(
                entity.id, agent, transform, target
            )

            # Apply steering force (truncate to max force)
            if steering_force.length > agent.max_force:
                steering_force = cast(
                    Vector2, steering_force.normalized() * agent.max_force
                )

            # Calculate acceleration (F = ma, so a = F/m)
            acceleration = steering_force * (1.0 / agent.mass)

            # Update velocity
            new_velocity = agent.velocity + acceleration * dt
            if new_velocity.length > agent.max_speed:
                new_velocity = cast(
                    Vector2, new_velocity.normalized() * agent.max_speed
                )
            agent.velocity = new_velocity

            # ARRIVE must actually stop. The dt-scaled force above is only a
            # weak proportional brake, so on its own the agent overshoots the
            # target and orbits it forever. Enforce the arrive speed ramp on
            # the velocity directly: cap speed to max_speed * d / slowing_radius
            # inside the radius, and snap to rest at the target.
            if agent.behavior == SteeringBehaviorType.ARRIVE and target is not None:
                distance = (target - transform.position).length
                if distance <= _ARRIVE_STOP_DISTANCE:
                    agent.velocity = Vector2(0, 0)
                elif distance < agent.slowing_radius and agent.slowing_radius > 0:
                    ramp_speed = agent.max_speed * (distance / agent.slowing_radius)
                    if agent.velocity.length > ramp_speed:
                        agent.velocity = cast(
                            Vector2, agent.velocity.normalized() * ramp_speed
                        )

            # Update position
            transform.position = transform.position + agent.velocity * dt

            # Update Navigator waypoint progress if present
            if entity.has_component(Navigator) and target is not None:
                self._update_navigator(entity, transform, target)

    def _get_target(self, entity: Entity, agent: SteeringAgent) -> Vector2 | None:
        """Get the target position for steering.

        Args:
            entity: The entity being steered.
            agent: The steering agent component.

        Returns:
            Target position, or None if no target.
        """
        # Direct target takes precedence
        if agent.target is not None:
            return agent.target

        # Otherwise use Navigator path if available
        if entity.has_component(Navigator):
            navigator = entity.get_component(Navigator)
            return navigator.get_current_target()

        return None

    def _calculate_steering(
        self,
        entity_id: str,
        agent: SteeringAgent,
        transform: Transform,
        target: Vector2 | None,
    ) -> Vector2:
        """Calculate steering force based on behavior type.

        Args:
            entity_id: Entity ID for wander target persistence.
            agent: The steering agent component.
            transform: Entity transform.
            target: Target position (may be None for wander).

        Returns:
            Steering force vector.
        """
        behavior = agent.behavior

        if behavior == SteeringBehaviorType.WANDER:
            wander_target = self._wander_targets.get(entity_id)
            force, new_wander_target = SteeringBehavior.wander(
                transform,
                agent.max_speed,
                agent.velocity,
                wander_target=wander_target,
            )
            self._wander_targets[entity_id] = new_wander_target
            return force

        if target is None:
            return Vector2(0, 0)

        if behavior == SteeringBehaviorType.SEEK:
            return SteeringBehavior.seek(
                transform, target, agent.max_speed, agent.velocity
            )

        if behavior == SteeringBehaviorType.ARRIVE:
            return SteeringBehavior.arrive(
                transform, target, agent.max_speed, agent.velocity, agent.slowing_radius
            )

        if behavior == SteeringBehaviorType.FLEE:
            return SteeringBehavior.flee(
                transform, target, agent.max_speed, agent.velocity
            )

        if behavior == SteeringBehaviorType.PURSUIT:
            return SteeringBehavior.pursuit(
                transform,
                target,
                agent.target_velocity,
                agent.max_speed,
                agent.velocity,
            )

        # Only EVADE remains: WANDER returned above, and every other member is
        # handled just above; SteeringAgent.__post_init__ rejects anything else
        # at construction.
        return SteeringBehavior.evade(
            transform,
            target,
            agent.target_velocity,
            agent.max_speed,
            agent.velocity,
        )

    def _update_navigator(
        self, entity: Entity, transform: Transform, target: Vector2
    ) -> None:
        """Update Navigator waypoint progress.

        Args:
            entity: The entity with Navigator.
            transform: Entity transform.
            target: Current target waypoint.
        """
        navigator = entity.get_component(Navigator)
        distance = (target - transform.position).length

        if distance < navigator.reach_threshold:
            # Move to next waypoint
            navigator.current_index += 1

    def cleanup(self) -> None:
        """Clear all stored wander-target state.

        Called by SystemManager.cleanup() on scene exit -- the system dies
        with the scene, so per-entity tracking becomes moot.
        """
        self._wander_targets.clear()
