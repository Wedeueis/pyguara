"""Interfaces for physics engine adapters."""

from typing import Any, Protocol, runtime_checkable

from pyguara.common.types import Rect, Vector2
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    JointType,
    PhysicsMaterial,
    RaycastHit,
    ShapeType,
)


@runtime_checkable
class IPhysicsBody(Protocol):
    """Interface for a physics body handle."""

    @property
    def position(self) -> Vector2:
        """Get the body's world position."""
        ...

    @position.setter
    def position(self, value: Vector2) -> None:
        """Set the body's world position."""
        ...

    @property
    def rotation(self) -> float:
        """Get the body's rotation in degrees."""
        ...

    @rotation.setter
    def rotation(self, value: float) -> None:
        """Set the body's rotation in degrees."""
        ...

    @property
    def velocity(self) -> Vector2:
        """Get the linear velocity."""
        ...

    @velocity.setter
    def velocity(self, value: Vector2) -> None:
        """Set the linear velocity."""
        ...

    def apply_force(self, force: Vector2, point: Vector2 | None = None) -> None:
        """Apply a continuous force to the body."""
        ...

    def apply_impulse(self, impulse: Vector2, point: Vector2 | None = None) -> None:
        """Apply an instant impulse to the body."""
        ...


@runtime_checkable
class IPhysicsEngine(Protocol):
    """Interface for the core physics simulation engine."""

    def initialize(self, gravity: Vector2) -> None:
        """Initialize the physics world."""
        ...

    def cleanup(self) -> None:
        """Destroy the physics world and free resources."""
        ...

    def set_collision_system(self, collision_system: Any) -> None:
        """Register the object that collision callbacks are routed to.

        The engine calls `on_collision_begin`/`_persist`/`_end` on it for
        every contact pair. `bootstrap.py` wires the `CollisionSystem` here
        after construction.
        """
        ...

    def update(self, delta_time: float) -> None:
        """Step the simulation forward."""
        ...

    def create_body(
        self,
        entity_id: int | str,
        body_type: BodyType,
        position: Vector2,
        mass: float = 1.0,
        fixed_rotation: bool = False,
        gravity_scale: float = 1.0,
    ) -> IPhysicsBody:
        """Create and register a new physics body."""
        ...

    def destroy_body(self, body: IPhysicsBody) -> None:
        """Remove a body from the simulation."""
        ...

    def add_shape(
        self,
        body: IPhysicsBody,
        shape_type: ShapeType,
        dimensions: list[float],
        offset: Vector2,
        material: PhysicsMaterial,
        collision_layer: CollisionLayer,
        is_sensor: bool,
        one_way: bool = False,
        one_way_normal: Vector2 | None = None,
    ) -> Any:
        """Attach a collision shape to a body.

        Args:
            body: The body to attach to.
            shape_type: Circle, box, segment or polygon.
            dimensions: Radius, or width and height.
            offset: Local offset from the body's centre.
            material: Friction, restitution and density.
            collision_layer: Category, mask and group filtering.
            is_sensor: Detect overlaps without blocking.
            one_way: Solid from one side only.
            one_way_normal: Which side is solid, in world space. Defaults to
                `(0, -1)` -- up the screen -- when `one_way` is set.

        Returns:
            The backend's shape object.
        """
        ...

    def raycast(
        self,
        start: Vector2,
        end: Vector2,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> RaycastHit | None:
        """Cast a ray in the physics world.

        Args:
            start: Ray origin in world space.
            end: Ray end in world space.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Skip hits on this entity's own body. A character
                casting to find the ground beneath its feet starts the ray at
                its own edge and would otherwise detect itself.

        Returns:
            The nearest hit, or None.
        """
        ...

    def overlap_box(
        self,
        centre: Vector2,
        half_extents: Vector2,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> int | str | None:
        """Report which entity's solid shape an axis-aligned box overlaps.

        The question a character mover asks before committing a step: "if I
        were here, would I be inside something, and if so, what?" Knowing
        *what* -- not just whether -- is what lets a mover recognise a
        pushable crate rather than merely stopping at it. Sensors do not
        count -- they are meant to be passed through. Single-hit by design:
        this is the mover's per-step primitive and stops at the first solid.
        Use `overlap_box_all` when every overlapping entity is wanted.

        Args:
            centre: Box centre in world space.
            half_extents: Half width and half height.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Body to disregard, normally the mover itself.

        Returns:
            The entity id of the first solid, non-sensor shape found
            overlapping, or None if the box is clear.
        """
        ...

    def overlap_box_all(
        self,
        centre: Vector2,
        half_extents: Vector2,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> list[int | str]:
        """Report every entity whose solid shape an axis-aligned box overlaps.

        The multi-hit sibling of `overlap_box`: a box-shaped melee swing, a
        marquee selection in an editor, "everything on this tile". Sensors
        are skipped. A multi-shape entity is reported once.

        Args:
            centre: Box centre in world space.
            half_extents: Half width and half height.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Body to disregard.

        Returns:
            Entity ids of the solid, non-sensor shapes the box overlaps, in
            no guaranteed order. Empty when the box is clear.
        """
        ...

    def overlap_circle(
        self,
        centre: Vector2,
        radius: float,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> list[int | str]:
        """Report every entity whose solid shape a circle overlaps.

        Explosion radius, melee arc, "which enemies are within aggro range".
        Sensors are skipped. A multi-shape entity is reported once.

        Args:
            centre: Circle centre in world space.
            radius: Circle radius.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Body to disregard, normally the source.

        Returns:
            Entity ids of the solid, non-sensor shapes the circle overlaps,
            in no guaranteed order. Empty when nothing is in range.
        """
        ...

    def point_query(
        self,
        point: Vector2,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> list[int | str]:
        """Report every entity whose solid shape contains a world point.

        Click-picking: "what is under the cursor?". Sensors are skipped. A
        multi-shape entity is reported once. Results are ordered with the
        most deeply enclosing shape first, so `result[0]` is the best pick
        when several shapes stack under the point.

        Args:
            point: The world-space point to test.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Body to disregard.

        Returns:
            Entity ids under the point, most-enclosed first. Empty when the
            point is in open space.
        """
        ...

    def region_query(
        self,
        bounds: Rect,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> list[int | str]:
        """Report every entity whose *bounding box* overlaps a rectangle.

        The cheapest spatial test there is: it compares axis-aligned
        bounding boxes and never the shapes themselves, so a circle or a
        rotated polygon whose box reaches into `bounds` is reported even
        when the shape does not. Use it to cut a large world down to a
        candidate set fast, then confirm each with `overlap_box_all`,
        `overlap_circle` or a per-entity check. Sensors are skipped.

        Args:
            bounds: The world-space rectangle to test against.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Body to disregard.

        Returns:
            Entity ids whose bounding box overlaps `bounds`, in no
            guaranteed order. Empty when the rectangle is clear.
        """
        ...

    def raycast_all(
        self,
        start: Vector2,
        end: Vector2,
        mask: int = 0xFFFFFFFF,
        ignore_entity_id: int | str | None = None,
    ) -> list[RaycastHit]:
        """Cast a ray and return every shape along it, nearest first.

        A piercing shot or a hitscan laser that passes through several
        targets, where `raycast` (nearest hit only) would stop at the first.
        Sensors are skipped, matching `raycast`.

        Args:
            start: Ray origin in world space.
            end: Ray end in world space.
            mask: Collision mask; shapes outside it are ignored.
            ignore_entity_id: Skip hits on this entity's own body.

        Returns:
            Every hit between `start` and `end`, ordered by distance from
            `start`. Empty when the ray hits nothing.
        """
        ...

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
        """Create a joint/constraint between two bodies.

        Args:
            body_a: First physics body.
            body_b: Second physics body.
            joint_type: Type of joint (PIN, DISTANCE, SPRING, etc.).
            anchor_a: Local anchor point on body A.
            anchor_b: Local anchor point on body B.
            min_distance: Minimum distance (for DISTANCE/SLIDER joints).
            max_distance: Maximum distance (for DISTANCE/SLIDER joints).
            stiffness: Spring stiffness (for SPRING joints).
            damping: Spring damping (for SPRING joints).
            max_force: Maximum force limit (0 = infinite).
            collide_connected: Allow connected bodies to collide.

        Returns:
            Physics engine-specific joint handle.
        """
        ...

    def destroy_joint(self, joint_handle: Any) -> None:
        """Remove a joint from the simulation.

        Args:
            joint_handle: Physics engine-specific joint handle.
        """
        ...
