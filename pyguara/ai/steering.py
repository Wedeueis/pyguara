"""Steering behaviors for autonomous movement."""

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
        # FIX: Cast the result of vector math to Vector2
        desired = cast(Vector2, (target - transform.position).normalized() * max_speed)
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
