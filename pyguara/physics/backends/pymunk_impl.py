"""Pymunk implementation of the physics engine adapter."""

import math
from typing import Any, Dict, List, Optional, Union

import pymunk

from pyguara.common.types import Vector2
from pyguara.physics.protocols import IPhysicsBody, IPhysicsEngine
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    JointType,
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
        # Collision system for event routing (injected after construction)
        self._collision_system: Optional[Any] = None

    def initialize(self, gravity: Vector2) -> None:
        """Initialize the physics space with gravity."""
        self.space = pymunk.Space()
        self.space.gravity = (gravity.x, gravity.y)

        # Setup collision handlers if collision system is already registered
        if self._collision_system:
            self._setup_collision_handlers()

    def set_collision_system(self, collision_system: Any) -> None:
        """Register the CollisionSystem for event routing.

        Args:
            collision_system: CollisionSystem instance to handle callbacks.
        """
        self._collision_system = collision_system

        # Setup handlers if space is already initialized
        if self.space:
            self._setup_collision_handlers()

    def _setup_collision_handlers(self) -> None:
        """Configure pymunk collision handlers to route to CollisionSystem."""
        if not self.space:
            return

        # Default collision handler for all collision types
        handler = self.space.add_default_collision_handler()  # type: ignore[attr-defined]
        handler.begin = self._on_pymunk_begin
        handler.pre_solve = self._on_pymunk_persist
        handler.separate = self._on_pymunk_end

    def _on_pymunk_begin(
        self, arbiter: pymunk.Arbiter, space: pymunk.Space, data: dict
    ) -> bool:
        """Pymunk callback when collision begins.

        Args:
            arbiter: Pymunk collision arbiter with collision data.
            space: Pymunk space.
            data: User data dict.

        Returns:
            True to process collision, False to ignore.
        """
        if not self._collision_system:
            return True

        shape_a, shape_b = arbiter.shapes
        entity_a = getattr(shape_a.body, "entity_id", None)
        entity_b = getattr(shape_b.body, "entity_id", None)

        if entity_a is None or entity_b is None:
            return True

        # Extract collision details
        contact_points = arbiter.contact_point_set.points
        if contact_points:
            contact = contact_points[0]
            point = Vector2(contact.point_a.x, contact.point_a.y)
            normal = Vector2(contact.normal.x, contact.normal.y)  # type: ignore[attr-defined]
        else:
            point = Vector2.zero()
            normal = Vector2(0, 1)

        impulse = arbiter.total_impulse.length
        is_sensor = shape_a.sensor or shape_b.sensor

        return self._collision_system.on_collision_begin(  # type: ignore[no-any-return]
            str(entity_a), str(entity_b), point, normal, impulse, is_sensor
        )

    def _on_pymunk_persist(
        self, arbiter: pymunk.Arbiter, space: pymunk.Space, data: dict
    ) -> bool:
        """Pymunk callback during collision (each frame).

        Args:
            arbiter: Pymunk collision arbiter with collision data.
            space: Pymunk space.
            data: User data dict.

        Returns:
            True to continue processing, False to ignore.
        """
        if not self._collision_system:
            return True

        shape_a, shape_b = arbiter.shapes
        entity_a = getattr(shape_a.body, "entity_id", None)
        entity_b = getattr(shape_b.body, "entity_id", None)

        if entity_a is None or entity_b is None:
            return True

        # Extract collision details
        contact_points = arbiter.contact_point_set.points
        if contact_points:
            contact = contact_points[0]
            point = Vector2(contact.point_a.x, contact.point_a.y)
            normal = Vector2(contact.normal.x, contact.normal.y)  # type: ignore[attr-defined]
        else:
            point = Vector2.zero()
            normal = Vector2(0, 1)

        impulse = arbiter.total_impulse.length
        is_sensor = shape_a.sensor or shape_b.sensor

        return self._collision_system.on_collision_persist(  # type: ignore[no-any-return]
            str(entity_a), str(entity_b), point, normal, impulse, is_sensor
        )

    def _on_pymunk_end(
        self, arbiter: pymunk.Arbiter, space: pymunk.Space, data: dict
    ) -> None:
        """Pymunk callback when collision ends.

        Args:
            arbiter: Pymunk collision arbiter.
            space: Pymunk space.
            data: User data dict.
        """
        if not self._collision_system:
            return

        shape_a, shape_b = arbiter.shapes
        entity_a = getattr(shape_a.body, "entity_id", None)
        entity_b = getattr(shape_b.body, "entity_id", None)

        if entity_a is None or entity_b is None:
            return

        is_sensor = shape_a.sensor or shape_b.sensor

        self._collision_system.on_collision_end(str(entity_a), str(entity_b), is_sensor)

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

    def create_joint(
        self,
        body_a: IPhysicsBody,
        body_b: IPhysicsBody,
        joint_type: JointType,
        anchor_a: Vector2,
        anchor_b: Vector2,
        min_distance: float,
        max_distance: float,
        stiffness: float,
        damping: float,
        max_force: float,
        collide_connected: bool,
    ) -> Any:
        """Create a pymunk constraint between two bodies.

        Args:
            body_a: First physics body.
            body_b: Second physics body.
            joint_type: Type of joint to create.
            anchor_a: Local anchor point on body A.
            anchor_b: Local anchor point on body B.
            min_distance: Minimum distance for distance/slider joints.
            max_distance: Maximum distance for distance/slider joints.
            stiffness: Spring stiffness coefficient.
            damping: Spring damping coefficient.
            max_force: Maximum force the joint can apply (0 = infinite).
            collide_connected: Whether connected bodies can collide.

        Returns:
            Pymunk constraint object.
        """
        if not self.space:
            return None

        if not isinstance(body_a, PymunkBodyAdapter) or not isinstance(
            body_b, PymunkBodyAdapter
        ):
            raise TypeError("Invalid body handles for Pymunk backend")

        pm_body_a = body_a._body
        pm_body_b = body_b._body

        constraint: Optional[pymunk.Constraint] = None

        if joint_type == JointType.PIN:
            # Pin joint (revolute) - allows rotation around shared point
            constraint = pymunk.PinJoint(
                pm_body_a, pm_body_b, (anchor_a.x, anchor_a.y), (anchor_b.x, anchor_b.y)
            )

        elif joint_type == JointType.DISTANCE:
            # Distance joint - maintains fixed or bounded distance
            if min_distance == max_distance:
                # Fixed distance - use damped spring with high stiffness
                constraint = pymunk.DampedSpring(
                    pm_body_a,
                    pm_body_b,
                    (anchor_a.x, anchor_a.y),
                    (anchor_b.x, anchor_b.y),
                    rest_length=min_distance,
                    stiffness=10000.0,  # Very stiff for rigid connection
                    damping=100.0,
                )
            else:
                # Bounded distance - use slide joint
                constraint = pymunk.SlideJoint(
                    pm_body_a,
                    pm_body_b,
                    (anchor_a.x, anchor_a.y),
                    (anchor_b.x, anchor_b.y),
                    min_distance,
                    max_distance,
                )

        elif joint_type == JointType.SPRING:
            # Spring-damper joint
            constraint = pymunk.DampedSpring(
                pm_body_a,
                pm_body_b,
                (anchor_a.x, anchor_a.y),
                (anchor_b.x, anchor_b.y),
                rest_length=min_distance,  # Use min_distance as rest length
                stiffness=stiffness,
                damping=damping,
            )

        elif joint_type == JointType.SLIDER:
            # Slider/prismatic joint
            constraint = pymunk.SlideJoint(
                pm_body_a,
                pm_body_b,
                (anchor_a.x, anchor_a.y),
                (anchor_b.x, anchor_b.y),
                min_distance,
                max_distance,
            )

        elif joint_type == JointType.GEAR:
            # Gear joint - links rotation
            constraint = pymunk.GearJoint(pm_body_a, pm_body_b, phase=0.0, ratio=1.0)

        elif joint_type == JointType.MOTOR:
            # Simple motor - applies rotational force
            constraint = pymunk.SimpleMotor(pm_body_a, pm_body_b, rate=0.0)

        if constraint:
            # Apply max force limit if specified
            if max_force > 0:
                constraint.max_force = max_force

            # Set collision behavior
            constraint.collide_bodies = collide_connected

            # Add to space
            self.space.add(constraint)

        return constraint

    def destroy_joint(self, joint_handle: Any) -> None:
        """Remove a joint from the simulation.

        Args:
            joint_handle: Pymunk constraint object to remove.
        """
        if self.space and joint_handle:
            try:
                self.space.remove(joint_handle)
            except Exception:
                # Joint may have already been removed
                pass
