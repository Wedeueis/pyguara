"""Steering behaviors for autonomous movement."""

import math
import random
from typing import cast

from pyguara.common.components import Transform
from pyguara.common.types import Vector2


class SteeringBehavior:
    """Calculates forces to move an entity in a natural way."""

    @staticmethod
    def seek(
        transform: Transform,
        target: Vector2,
        max_speed: float,
        current_velocity: Vector2,
    ) -> Vector2:
        """Calculate steering force to move toward a target."""
        direction = target - transform.position
        if direction.length < 0.001:
            return Vector2(0, 0)
        desired = cast(Vector2, direction.normalized() * max_speed)
        return desired - current_velocity

    @staticmethod
    def flee(
        transform: Transform,
        threat: Vector2,
        max_speed: float,
        current_velocity: Vector2,
        panic_distance: float = 200.0,
    ) -> Vector2:
        """
        Calculate steering force to flee from a threat.

        Args:
            transform: Entity transform.
            threat: Position to flee from.
            max_speed: Max movement speed.
            current_velocity: Current entity velocity.
            panic_distance: Only flee if within this distance.
        """
        direction = transform.position - threat
        distance = direction.length

        if distance > panic_distance:
            return Vector2(0, 0)

        if distance < 0.001:
            # If on top of threat, flee in random direction
            angle = random.uniform(0, 2 * math.pi)
            direction = Vector2(math.cos(angle), math.sin(angle))
        else:
            direction = cast(Vector2, direction.normalized())

        desired = direction * max_speed
        return desired - current_velocity

    @staticmethod
    def arrive(
        transform: Transform,
        target: Vector2,
        max_speed: float,
        current_velocity: Vector2,
        slowing_radius: float = 100.0,
    ) -> Vector2:
        """
        Calculate steering force to arrive at a target and stop.

        Args:
            transform: Entity transform.
            target: Target position.
            max_speed: Max movement speed.
            current_velocity: Current entity velocity.
            slowing_radius: Distance at which to start slowing down.
        """
        direction = target - transform.position
        distance = direction.length

        if distance < 0.1:
            # Stop completely - return inverse of current velocity to cancel it out
            return -current_velocity

        if distance < slowing_radius:
            target_speed = max_speed * (distance / slowing_radius)
        else:
            target_speed = max_speed

        desired = cast(Vector2, direction.normalized() * target_speed)
        return desired - current_velocity

    @staticmethod
    def wander(
        transform: Transform,
        max_speed: float,
        current_velocity: Vector2,
        wander_radius: float = 50.0,
        wander_distance: float = 80.0,
        wander_jitter: float = 20.0,
        wander_target: Vector2 | None = None,
    ) -> tuple[Vector2, Vector2]:
        """
        Calculate steering force for random wandering behavior.

        Uses a circle projected in front of the entity with a random target
        on its circumference.

        Args:
            transform: Entity transform.
            max_speed: Max movement speed.
            current_velocity: Current entity velocity.
            wander_radius: Radius of the wander circle.
            wander_distance: How far ahead the wander circle is projected.
            wander_jitter: Amount of random displacement per frame.
            wander_target: Previous wander target on circle (or None to create).

        Returns:
            Tuple of (steering_force, new_wander_target) for state persistence.
        """
        # Initialize or jitter the wander target
        if wander_target is None:
            angle = random.uniform(0, 2 * math.pi)
            wander_target = Vector2(
                math.cos(angle) * wander_radius, math.sin(angle) * wander_radius
            )
        else:
            # Add random jitter
            jitter = Vector2(
                random.uniform(-1, 1) * wander_jitter,
                random.uniform(-1, 1) * wander_jitter,
            )
            wander_target = wander_target + jitter
            # Re-project onto circle
            if wander_target.length > 0.001:
                wander_target = cast(
                    Vector2, wander_target.normalized() * wander_radius
                )

        # Calculate world position of wander target
        if current_velocity.length > 0.001:
            forward = current_velocity.normalized()
        else:
            # Default forward direction if stationary
            forward = Vector2(1, 0)

        # Project circle center ahead of agent
        circle_center = transform.position + forward * wander_distance
        target_world = circle_center + wander_target

        # Seek toward wander target
        desired = cast(
            Vector2, (target_world - transform.position).normalized() * max_speed
        )
        steering = desired - current_velocity

        return steering, wander_target

    @staticmethod
    def pursuit(
        transform: Transform,
        target_position: Vector2,
        target_velocity: Vector2,
        max_speed: float,
        current_velocity: Vector2,
    ) -> Vector2:
        """
        Calculate steering force to intercept a moving target.

        Args:
            transform: Entity transform.
            target_position: Current position of the target.
            target_velocity: Current velocity of the target.
            max_speed: Max movement speed.
            current_velocity: Current entity velocity.
        """
        to_target = target_position - transform.position
        distance = to_target.length

        if distance < 0.001:
            return Vector2(0, 0)

        # Estimate time to reach target
        relative_speed = max_speed + target_velocity.length
        if relative_speed < 0.001:
            look_ahead_time = 1.0
        else:
            look_ahead_time = distance / relative_speed

        # Predict future position
        future_position = target_position + target_velocity * look_ahead_time

        return SteeringBehavior.seek(
            transform, future_position, max_speed, current_velocity
        )

    @staticmethod
    def evade(
        transform: Transform,
        threat_position: Vector2,
        threat_velocity: Vector2,
        max_speed: float,
        current_velocity: Vector2,
        panic_distance: float = 200.0,
    ) -> Vector2:
        """
        Calculate steering force to evade a moving threat.

        Args:
            transform: Entity transform.
            threat_position: Current position of the threat.
            threat_velocity: Current velocity of the threat.
            max_speed: Max movement speed.
            current_velocity: Current entity velocity.
            panic_distance: Only evade if within this distance.
        """
        to_threat = threat_position - transform.position
        distance = to_threat.length

        if distance > panic_distance:
            return Vector2(0, 0)

        # Estimate time to intercept
        relative_speed = max_speed + threat_velocity.length
        if relative_speed < 0.001:
            look_ahead_time = 1.0
        else:
            look_ahead_time = distance / relative_speed

        # Predict future position of threat
        future_position = threat_position + threat_velocity * look_ahead_time

        return SteeringBehavior.flee(
            transform, future_position, max_speed, current_velocity, panic_distance * 2
        )
