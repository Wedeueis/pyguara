"""Pymunk implementation of the physics engine adapter."""

import math
from typing import Any, Dict, List, Optional, Union

import pymunk

from pyguara.common.types import Vector2
from pyguara.physics.protocols import IPhysicsBody, IPhysicsEngine
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    PhysicsMaterial,
    RaycastHit,
    ShapeType,
)


class PymunkBodyAdapter(IPhysicsBody):
    """Wrapper around pymunk.Body to conform to IPhysicsBody."""

    def __init__(self, body: pymunk.Body) -> None:
        """Initialize the adapter with a pymunk Body."""
        self._body = body

    @property
    def position(self) -> Vector2:
        """Get the body's world position."""
        return Vector2(self._body.position.x, self._body.position.y)

    @position.setter
    def position(self, value: Vector2) -> None:
        """Set the body's world position."""
        self._body.position = value.x, value.y

    @property
    def rotation(self) -> float:
        """Get the body's rotation in degrees."""
        return math.degrees(self._body.angle)

    @rotation.setter
    def rotation(self, value: float) -> None:
        """Set the body's rotation in degrees."""
        self._body.angle = math.radians(value)

    @property
    def velocity(self) -> Vector2:
        """Get the linear velocity."""
        return Vector2(self._body.velocity.x, self._body.velocity.y)

    @velocity.setter
    def velocity(self, value: Vector2) -> None:
        """Set the linear velocity."""
        self._body.velocity = value.x, value.y

    def apply_force(self, force: Vector2, point: Optional[Vector2] = None) -> None:
        """Apply a continuous force to the body."""
        p = (point.x, point.y) if point else (0, 0)
        self._body.apply_force_at_local_point((force.x, force.y), p)

    def apply_impulse(self, impulse: Vector2, point: Optional[Vector2] = None) -> None:
        """Apply an instant impulse to the body."""
        p = (point.x, point.y) if point else (0, 0)
        self._body.apply_impulse_at_local_point((impulse.x, impulse.y), p)


class PymunkEngine(IPhysicsEngine):
    """Pymunk backend implementation."""

    def __init__(self) -> None:
        """Initialize the Pymunk engine wrapper."""
        self.space: Optional[pymunk.Space] = None
        # Map entity_id -> PymunkBodyAdapter
        self._bodies: Dict[Union[int, str], PymunkBodyAdapter] = {}

    def initialize(self, gravity: Vector2) -> None:
        """Initialize the physics space with gravity."""
        self.space = pymunk.Space()
        self.space.gravity = (gravity.x, gravity.y)

    def update(self, delta_time: float) -> None:
        """Step the physics simulation forward."""
        if self.space:
            self.space.step(delta_time)

    def create_body(
        self, entity_id: Union[int, str], body_type: BodyType, position: Vector2
    ) -> IPhysicsBody:
        """Create and register a new physics body."""
        if not self.space:
            raise RuntimeError("Physics engine not initialized")

        pm_type = pymunk.Body.DYNAMIC
        if body_type == BodyType.STATIC:
            pm_type = pymunk.Body.STATIC
        elif body_type == BodyType.KINEMATIC:
            pm_type = pymunk.Body.KINEMATIC

        body = pymunk.Body(body_type=pm_type)
        body.position = (position.x, position.y)

        # Store entity ID on body for collisions
        body.entity_id = entity_id

        self.space.add(body)

        adapter = PymunkBodyAdapter(body)
        self._bodies[entity_id] = adapter
        return adapter

    def destroy_body(self, body_handle: IPhysicsBody) -> None:
        """Remove a body from the simulation."""
        # Implementation to remove body and shapes from space
        pass

    def add_shape(
        self,
        body_handle: IPhysicsBody,
        shape_type: ShapeType,
        dimensions: List[float],
        offset: Vector2,
        material: PhysicsMaterial,
        collision_layer: CollisionLayer,
        is_sensor: bool,
    ) -> Any:
        """Attach a collision shape to a body."""
        if not self.space:
            return None

        if not isinstance(body_handle, PymunkBodyAdapter):
            raise TypeError("Invalid body handle for Pymunk backend")

        body = body_handle._body
        shape: Optional[pymunk.Shape] = None

        if shape_type == ShapeType.CIRCLE:
            radius = dimensions[0]
            shape = pymunk.Circle(body, radius, (offset.x, offset.y))
        elif shape_type == ShapeType.BOX:
            width, height = dimensions
            # Pymunk Box is a Poly
            shape = pymunk.Poly.create_box(body, size=(width, height))

        if shape:
            shape.density = material.density
            shape.friction = material.friction
            shape.elasticity = material.restitution
            shape.sensor = is_sensor

            # Bitmask filtering
            filter = pymunk.ShapeFilter(
                categories=collision_layer.category,
                mask=collision_layer.mask,
                group=collision_layer.group,
            )
            shape.filter = filter

            self.space.add(shape)
            return shape

    def raycast(
        self, start: Vector2, end: Vector2, mask: int = 0xFFFFFFFF
    ) -> Optional[RaycastHit]:
        """Perform a raycast query."""
        if not self.space:
            return None

        query = self.space.segment_query_first(
            (start.x, start.y),
            (end.x, end.y),
            1.0,  # Radius
            pymunk.ShapeFilter(mask=mask),
        )

        if query:
            return RaycastHit(
                position=Vector2(query.point.x, query.point.y),
                normal=Vector2(query.normal.x, query.normal.y),
                distance=start.distance_to(Vector2(query.point.x, query.point.y)),
                entity_id=getattr(query.shape.body, "entity_id", None),
            )
        return None
