"""Pymunk implementation of the physics engine adapter."""

import contextlib
import math
from typing import Any

import pymunk

from pyguara.common.types import Vector2
from pyguara.physics.protocols import IPhysicsBody
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    JointType,
    PhysicsMaterial,
    RaycastHit,
    ShapeType,
)

# One 1/60s step lets a body jump velocity/60 pixels; at 600 px/s that is 10
# pixels, which clears a 10px wall outright. Four substeps put the threshold
# above the speeds a platformer reaches under normal gravity, at four times
# the solver cost -- cheap for the body counts a 2D game runs.
DEFAULT_SUBSTEPS = 4

# Ray queries are swept circles in Chipmunk. Keep the radius small: it
# widens what the ray can touch, including the caster's own collider.
RAYCAST_RADIUS = 1.0


class PymunkBodyAdapter:
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

    def apply_force(self, force: Vector2, point: Vector2 | None = None) -> None:
        """Apply a continuous force to the body."""
        p = (point.x, point.y) if point else (0, 0)
        self._body.apply_force_at_local_point((force.x, force.y), p)

    def apply_impulse(self, impulse: Vector2, point: Vector2 | None = None) -> None:
        """Apply an instant impulse to the body."""
        p = (point.x, point.y) if point else (0, 0)
        self._body.apply_impulse_at_local_point((impulse.x, impulse.y), p)


class PymunkEngine:
    """Pymunk backend implementation."""

    def __init__(self, substeps: int = DEFAULT_SUBSTEPS) -> None:
        """Initialize the Pymunk engine wrapper.

        Args:
            substeps: How many solver steps one call to `update()` becomes.
                Chipmunk has no continuous collision detection, so a body
                moves `velocity * dt` in a straight jump each step and passes
                through anything thinner than that jump. Substepping shortens
                the jump proportionally: each doubling roughly doubles the
                speed a thin wall can stop.

        Raises:
            ValueError: If `substeps` is not positive. Zero would step the
                simulation not at all and negative is meaningless; both are
                far better caught here than as a frozen world.
        """
        if substeps <= 0:
            raise ValueError(
                f"substeps must be positive, got {substeps}. It is the number "
                f"of solver steps per update; 1 disables substepping."
            )
        self._substeps = substeps
        self.space: pymunk.Space | None = None
        # Map entity_id -> PymunkBodyAdapter
        self._bodies: dict[int | str, PymunkBodyAdapter] = {}
        # Collision system for event routing (injected after construction)
        self._collision_system: Any | None = None

    def initialize(self, gravity: Vector2) -> None:
        """Initialize the physics space with gravity."""
        self.space = pymunk.Space()
        self.space.gravity = (gravity.x, gravity.y)

        # Setup collision handlers if collision system is already registered
        if self._collision_system:
            self._setup_collision_handlers()

    def cleanup(self) -> None:
        """Destroy the pymunk Space to prevent dangling callbacks."""
        if self.space:
            # Clear the default collision handler so callbacks cannot fire
            # while the space is being torn down. Tolerated if it fails: the
            # space may already be closing.
            with contextlib.suppress(Exception):
                self.space.on_collision(
                    begin=None, pre_solve=None, post_solve=None, separate=None
                )

            try:
                # Explicitly remove everything to ensure internal iterators don't run
                # during garbage collection
                if self.space.constraints:
                    self.space.remove(*self.space.constraints)
                if self.space.shapes:
                    self.space.remove(*self.space.shapes)
                if self.space.bodies:
                    self.space.remove(*self.space.bodies)
            except Exception:
                # Ignore errors during object removal
                pass

            self.space = None
            self._bodies.clear()
            self._collision_system = None

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
        # Pymunk 7.0+ uses on_collision(None, None) for default handler
        self.space.on_collision(
            begin=self._on_pymunk_begin,  # type: ignore[arg-type]
            pre_solve=self._on_pymunk_persist,  # type: ignore[arg-type]
            separate=self._on_pymunk_end,
        )

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
        contact_point_set = arbiter.contact_point_set
        if contact_point_set.points:
            contact = contact_point_set.points[0]
            point = Vector2(contact.point_a.x, contact.point_a.y)
            normal = Vector2(contact_point_set.normal.x, contact_point_set.normal.y)
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
        contact_point_set = arbiter.contact_point_set
        if contact_point_set.points:
            contact = contact_point_set.points[0]
            point = Vector2(contact.point_a.x, contact.point_a.y)
            normal = Vector2(contact_point_set.normal.x, contact_point_set.normal.y)
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
        """Step the physics simulation forward.

        Splits the tick into `substeps` equal solver steps. The step size is
        what decides whether a fast body is caught or passes through a thin
        collider, and it is deliberately derived from a fixed count rather
        than from the bodies' speeds: this engine supports deterministic
        replay, so the number of steps must not depend on the simulation's
        own state.

        Args:
            delta_time: Seconds to advance, normally one fixed tick.
        """
        if not self.space:
            return
        step = delta_time / self._substeps
        for _ in range(self._substeps):
            self.space.step(step)

    def create_body(
        self,
        entity_id: int | str,
        body_type: BodyType,
        position: Vector2,
        mass: float = 1.0,
    ) -> IPhysicsBody:
        """Create and register a new physics body."""
        if not self.space:
            raise RuntimeError(
                "Physics engine not initialized. Call initialize(gravity) first."
            )

        pm_type = pymunk.Body.DYNAMIC
        if body_type == BodyType.STATIC:
            pm_type = pymunk.Body.STATIC
        elif body_type == BodyType.KINEMATIC:
            pm_type = pymunk.Body.KINEMATIC

        # For dynamic bodies, set mass and moment (moment will be recalculated when shape is added)
        # Use a default moment based on mass; actual moment is set when shape is attached
        if pm_type == pymunk.Body.DYNAMIC:
            # Use a placeholder moment; it will be overwritten by add_shape
            moment = pymunk.moment_for_box(mass, (32, 32))
            body = pymunk.Body(mass=mass, moment=moment, body_type=pm_type)
        else:
            body = pymunk.Body(body_type=pm_type)

        body.position = (position.x, position.y)

        # Store entity ID on body for collisions
        body.entity_id = entity_id

        self.space.add(body)

        adapter = PymunkBodyAdapter(body)
        self._bodies[entity_id] = adapter
        return adapter

    def destroy_body(self, body_handle: IPhysicsBody) -> None:
        """Remove a body and its attached shapes from the simulation.

        Pymunk's own `body.shapes` is authoritative for what's attached, so
        no separate adapter-level shape tracking is needed.
        """
        if not self.space:
            return

        if not isinstance(body_handle, PymunkBodyAdapter):
            raise TypeError(
                f"Invalid body handle for Pymunk backend: expected PymunkBodyAdapter, "
                f"got {type(body_handle).__name__}"
            )

        body = body_handle._body
        for shape in list(body.shapes):
            self.space.remove(shape)
        self.space.remove(body)
        self._bodies.pop(body.entity_id, None)

    def add_shape(
        self,
        body_handle: IPhysicsBody,
        shape_type: ShapeType,
        dimensions: list[float],
        offset: Vector2,
        material: PhysicsMaterial,
        collision_layer: CollisionLayer,
        is_sensor: bool,
    ) -> Any:
        """Attach a collision shape to a body."""
        if not self.space:
            return None

        if not isinstance(body_handle, PymunkBodyAdapter):
            raise TypeError(
                f"Invalid body handle for Pymunk backend: expected PymunkBodyAdapter, "
                f"got {type(body_handle).__name__}"
            )

        body = body_handle._body
        shape: pymunk.Shape | None = None

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
        self,
        start: Vector2,
        end: Vector2,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> RaycastHit | None:
        """Perform a raycast query.

        Args:
            start: Ray origin in world space.
            end: Ray end in world space.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Skip hits on this entity's own body.

        Returns:
            The nearest hit that is not excluded, or None.
        """
        if not self.space:
            return None

        shape_filter = pymunk.ShapeFilter(mask=mask)

        if ignore_entity_id is None:
            query = self.space.segment_query_first(
                (start.x, start.y), (end.x, end.y), RAYCAST_RADIUS, shape_filter
            )
            return self._to_hit(query, start)

        # segment_query_first cannot exclude one body, so take every hit and
        # return the nearest that is not the caster's own. A character casting
        # for the ground under its feet starts the ray at its own edge, and a
        # self-hit reads as permanently grounded.
        hits = self.space.segment_query(
            (start.x, start.y), (end.x, end.y), RAYCAST_RADIUS, shape_filter
        )
        for hit in sorted(hits, key=lambda h: h.alpha):
            if getattr(hit.shape.body, "entity_id", None) != ignore_entity_id:
                return self._to_hit(hit, start)
        return None

    @staticmethod
    def _to_hit(query: Any, start: Vector2) -> RaycastHit | None:
        """Convert a pymunk query result into a `RaycastHit`.

        Args:
            query: A pymunk segment query result, or None.
            start: The ray origin, for computing distance.

        Returns:
            The hit, or None when the query found nothing.
        """
        if not query:
            return None
        point = Vector2(query.point.x, query.point.y)
        return RaycastHit(
            position=point,
            normal=Vector2(query.normal.x, query.normal.y),
            distance=start.distance_to(point),
            entity_id=getattr(query.shape.body, "entity_id", None),
        )

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
            raise TypeError(
                f"Invalid body handles for Pymunk backend: expected PymunkBodyAdapter, "
                f"got {type(body_a).__name__} and {type(body_b).__name__}"
            )

        pm_body_a = body_a._body
        pm_body_b = body_b._body

        constraint: pymunk.Constraint | None = None

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
            # The joint may already have been removed with its bodies.
            with contextlib.suppress(Exception):
                self.space.remove(joint_handle)
