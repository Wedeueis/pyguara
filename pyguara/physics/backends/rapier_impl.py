"""The Rapier physics backend, beside pymunk until it matches it.

`RapierEngine` keeps `IPhysicsEngine`'s contract over a Rapier world held
in the native extension (`rust/src/physics.rs`). It is chosen with
`physics.backend = "rapier"`; pymunk stays the default (roadmap 6e).

Joints, one-way platforms, segment and polygon shapes, sleeping and the
optional `sweep_box`/`step_bodies` capabilities are not implemented yet:
the first three raise, and a caller of the last two falls back as it does
for any engine without them. Known differences from pymunk are in
`docs/physics/simulation.md`.
"""

from __future__ import annotations

import math
from typing import Any

from pyguara.common.types import Rect, Vector2
from pyguara.log import get_logger
from pyguara.native import require_extension
from pyguara.physics.protocols import IPhysicsBody
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    JointType,
    PhysicsMaterial,
    RaycastHit,
    ShapeType,
)

logger = get_logger(__name__)

DEFAULT_SUBSTEPS = 4

_FULL_MASK = 0xFFFFFFFF

_KINDS = {BodyType.STATIC: 0, BodyType.KINEMATIC: 1, BodyType.DYNAMIC: 2}

# Collision event kinds, as `NativePhysicsWorld.take_events` reports them.
_BEGIN, _PERSIST, _END = 0, 1, 2


class RapierBody:
    """A body in a `RapierEngine`, conforming to `IPhysicsBody`."""

    def __init__(self, engine: RapierEngine, handle: int, entity_id: int | str) -> None:
        """Wrap a native body handle.

        Args:
            engine: The engine that owns the body.
            handle: The native body handle.
            entity_id: The owning entity.
        """
        self._engine = engine
        self._handle = handle
        self.entity_id = entity_id

    @property
    def position(self) -> Vector2:
        """Get the body's world position."""
        x, y, _, _, _ = self._engine._world().state(self._handle)
        return Vector2(x, y)

    @position.setter
    def position(self, value: Vector2) -> None:
        """Set the body's world position."""
        self._engine._world().set_position(self._handle, value.x, value.y)

    @property
    def rotation(self) -> float:
        """Get the body's rotation in degrees."""
        return math.degrees(self._engine._world().state(self._handle)[2])

    @rotation.setter
    def rotation(self, value: float) -> None:
        """Set the body's rotation in degrees."""
        self._engine._world().set_rotation(self._handle, math.radians(value))

    @property
    def velocity(self) -> Vector2:
        """Get the linear velocity."""
        _, _, _, vx, vy = self._engine._world().state(self._handle)
        return Vector2(vx, vy)

    @velocity.setter
    def velocity(self, value: Vector2) -> None:
        """Set the linear velocity."""
        self._engine._world().set_velocity(self._handle, value.x, value.y)

    def apply_force(self, force: Vector2, point: Vector2 | None = None) -> None:
        """Apply a force at a point in the body's frame, for the next solver step."""
        px, py = (point.x, point.y) if point else (0.0, 0.0)
        self._engine._world().apply_force(self._handle, force.x, force.y, px, py)

    def apply_impulse(self, impulse: Vector2, point: Vector2 | None = None) -> None:
        """Apply an instant impulse at a point in the body's frame."""
        px, py = (point.x, point.y) if point else (0.0, 0.0)
        self._engine._world().apply_impulse(self._handle, impulse.x, impulse.y, px, py)


class RapierEngine:
    """`IPhysicsEngine` over a native Rapier world."""

    def __init__(self, substeps: int = DEFAULT_SUBSTEPS) -> None:
        """Configure the engine; `initialize` builds the world.

        Args:
            substeps: Solver steps per `update()`, each of `delta_time /
                substeps`, as the pymunk backend splits a tick.

        Raises:
            ValueError: If `substeps` is below 1.
        """
        if substeps < 1:
            raise ValueError(f"substeps must be at least 1, got {substeps}")
        self._substeps = substeps
        self._native: Any = None
        self._collision_system: Any | None = None
        self._bodies: dict[int | str, RapierBody] = {}
        # Native owner slot <-> entity id. A slot, not the id itself,
        # because an entity id may be a string.
        self._owners: dict[int, int | str] = {}
        self._slots: dict[int | str, int] = {}
        self._released: list[int] = []
        self._next_slot = 1

    def _world(self) -> Any:
        """Return the native world.

        Raises:
            RuntimeError: If `initialize` has not run.
        """
        if self._native is None:
            raise RuntimeError(
                "Physics engine not initialized. Call initialize(gravity) first."
            )
        return self._native

    def _slot_of(self, entity_id: int | str | None) -> int | None:
        """Return the owner slot of an entity, or None."""
        return None if entity_id is None else self._slots.get(entity_id)

    def _entity_of(self, slot: int) -> int | str | None:
        """Return the entity owning a slot, or None."""
        return self._owners.get(slot)

    def initialize(self, gravity: Vector2) -> None:
        """Create the world with `gravity`, in pixels per second squared."""
        extension = require_extension("RapierEngine")
        self._native = extension.NativePhysicsWorld(
            gravity.x, gravity.y, self._substeps
        )
        self._native.set_reporting(self._collision_system is not None)
        self._bodies.clear()
        self._owners.clear()
        self._slots.clear()
        self._released.clear()

    def cleanup(self) -> None:
        """Drop the world and every body in it."""
        self._native = None
        self._bodies.clear()
        self._owners.clear()
        self._slots.clear()
        self._released.clear()
        self._collision_system = None

    def set_collision_system(self, collision_system: Any) -> None:
        """Route collision begin, persist and end to `collision_system`.

        None stops reporting, which also stops paying for it.
        """
        self._collision_system = collision_system
        if self._native is not None:
            self._native.set_reporting(collision_system is not None)

    def update(self, delta_time: float) -> None:
        """Step the world, then report the step's collisions in order.

        Events are reported after the step, not during it. A pair whose
        `on_collision_begin` returns False stops being resolved from the
        next solver step, where pymunk stops at once; it is still reported
        while it overlaps, as pymunk reports it.
        """
        if self._native is None:
            return
        self._native.step(delta_time)
        self._dispatch(self._native.take_events())
        for slot in self._released:
            self._owners.pop(slot, None)
        self._released.clear()

    def _dispatch(self, events: list[tuple[Any, ...]]) -> None:
        """Hand the native events to the collision system."""
        system = self._collision_system
        if system is None:
            return
        for (
            kind,
            collider_a,
            collider_b,
            slot_a,
            slot_b,
            x,
            y,
            normal_x,
            normal_y,
            impulse,
            sensor_slot,
        ) in events:
            entity_a = self._entity_of(slot_a)
            entity_b = self._entity_of(slot_b)
            if entity_a is None or entity_b is None:
                continue
            sensor = None if sensor_slot is None else self._entity_of(sensor_slot)
            sensor_id = None if sensor is None else str(sensor)
            if kind == _END:
                system.on_collision_end(str(entity_a), str(entity_b), sensor_id)
                continue
            handler = (
                system.on_collision_begin
                if kind == _BEGIN
                else system.on_collision_persist
            )
            process = handler(
                str(entity_a),
                str(entity_b),
                Vector2(x, y),
                Vector2(normal_x, normal_y),
                impulse,
                sensor_id,
            )
            if not process:
                self._world().suppress(collider_a, collider_b)

    def create_body(
        self,
        entity_id: int | str,
        body_type: BodyType,
        position: Vector2,
        mass: float = 1.0,
        fixed_rotation: bool = False,
        gravity_scale: float = 1.0,
    ) -> IPhysicsBody:
        """Create and register a new physics body.

        `mass` holds only until a collider with density is attached, which
        replaces it with the collider's own mass, as Chipmunk does.

        Raises:
            RuntimeError: If the engine has not been initialized.
        """
        world = self._world()
        slot = self._next_slot
        self._next_slot += 1
        handle = world.create_body(
            _KINDS[body_type],
            position.x,
            position.y,
            mass,
            fixed_rotation,
            gravity_scale,
            slot,
        )
        body = RapierBody(self, handle, entity_id)
        self._bodies[entity_id] = body
        self._owners[slot] = entity_id
        self._slots[entity_id] = slot
        return body

    def destroy_body(self, body: IPhysicsBody) -> None:
        """Remove a body and its colliders.

        Raises:
            TypeError: If the handle is not one of this backend's bodies.
        """
        if not isinstance(body, RapierBody):
            raise TypeError(
                f"Invalid body handle for Rapier backend: expected RapierBody, "
                f"got {type(body).__name__}"
            )
        if self._native is None:
            return
        self._native.remove_body(body._handle)
        # The slot is kept until the end events that name it have been
        # reported, so it is released at the next update instead of now.
        self._bodies.pop(body.entity_id, None)
        slot = self._slots.pop(body.entity_id, None)
        if slot is not None:
            # The ends of its contacts are reported by the next update and
            # name this slot, so the mapping outlives the body until then.
            self._released.append(slot)

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
        """Attach a circle or box collider.

        Raises:
            TypeError: If the handle is not one of this backend's bodies.
            NotImplementedError: For a segment or polygon shape, or a
                one-way platform, which this backend does not do yet.
        """
        if not isinstance(body, RapierBody):
            raise TypeError(
                f"Invalid body handle for Rapier backend: expected RapierBody, "
                f"got {type(body).__name__}"
            )
        if one_way:
            raise NotImplementedError(
                "One-way platforms are not implemented by the Rapier backend yet; "
                'use physics.backend = "pymunk".'
            )
        if shape_type is ShapeType.CIRCLE:
            kind, first, second = "circle", dimensions[0], 0.0
        elif shape_type is ShapeType.BOX:
            kind, first, second = "box", dimensions[0], dimensions[1]
        else:
            raise NotImplementedError(
                f"{shape_type.name} colliders are not implemented by the Rapier "
                f"backend. Supported: {ShapeType.CIRCLE.name}, {ShapeType.BOX.name}."
            )
        return self._world().add_collider(
            body._handle,
            kind,
            first,
            second,
            offset.x,
            offset.y,
            material.friction,
            material.restitution,
            material.density,
            collision_layer.category & _FULL_MASK,
            collision_layer.mask & _FULL_MASK,
            collision_layer.group & _FULL_MASK,
            is_sensor,
        )

    def _entities(self, slots: list[int]) -> list[int | str]:
        """Map owner slots to entity ids, dropping any no longer known."""
        found = [self._entity_of(slot) for slot in slots]
        return [entity for entity in found if entity is not None]

    def raycast(
        self,
        start: Vector2,
        end: Vector2,
        mask: int = _FULL_MASK,
        ignore_entity_id: int | str | None = None,
    ) -> RaycastHit | None:
        """Return the nearest solid hit along a segment, or None."""
        hits = self.raycast_all(start, end, mask, ignore_entity_id)
        return hits[0] if hits else None

    def raycast_all(
        self,
        start: Vector2,
        end: Vector2,
        mask: int = _FULL_MASK,
        ignore_entity_id: int | str | None = None,
    ) -> list[RaycastHit]:
        """Return every solid hit along a segment, nearest first."""
        if self._native is None:
            return []
        rows = self._native.raycast_all(
            start.x,
            start.y,
            end.x,
            end.y,
            mask & _FULL_MASK,
            self._slot_of(ignore_entity_id),
        )
        hits = []
        for x, y, normal_x, normal_y, slot in rows:
            point = Vector2(x, y)
            hits.append(
                RaycastHit(
                    position=point,
                    normal=Vector2(normal_x, normal_y),
                    distance=start.distance_to(point),
                    entity_id=self._entity_of(slot),
                )
            )
        return hits

    def overlap_box(
        self,
        centre: Vector2,
        half_extents: Vector2,
        mask: int = _FULL_MASK,
        ignore_entity_id: int | str | None = None,
    ) -> int | str | None:
        """Return the first entity whose solid shape overlaps a box, or None."""
        found = self.overlap_box_all(centre, half_extents, mask, ignore_entity_id)
        return found[0] if found else None

    def overlap_box_all(
        self,
        centre: Vector2,
        half_extents: Vector2,
        mask: int = _FULL_MASK,
        ignore_entity_id: int | str | None = None,
    ) -> list[int | str]:
        """Return every entity whose solid shape overlaps a box."""
        if self._native is None:
            return []
        return self._entities(
            self._native.overlap_box(
                centre.x,
                centre.y,
                half_extents.x,
                half_extents.y,
                mask & _FULL_MASK,
                self._slot_of(ignore_entity_id),
            )
        )

    def overlap_circle(
        self,
        centre: Vector2,
        radius: float,
        mask: int = _FULL_MASK,
        ignore_entity_id: int | str | None = None,
    ) -> list[int | str]:
        """Return every entity whose solid shape overlaps a circle."""
        if self._native is None:
            return []
        return self._entities(
            self._native.overlap_circle(
                centre.x,
                centre.y,
                radius,
                mask & _FULL_MASK,
                self._slot_of(ignore_entity_id),
            )
        )

    def point_query(
        self,
        point: Vector2,
        mask: int = _FULL_MASK,
        ignore_entity_id: int | str | None = None,
    ) -> list[int | str]:
        """Return every entity whose solid shape contains a point, deepest first."""
        if self._native is None:
            return []
        return self._entities(
            self._native.point_query(
                point.x, point.y, mask & _FULL_MASK, self._slot_of(ignore_entity_id)
            )
        )

    def region_query(
        self,
        bounds: Rect,
        mask: int = _FULL_MASK,
        ignore_entity_id: int | str | None = None,
    ) -> list[int | str]:
        """Return every entity whose bounding box overlaps a rectangle."""
        if self._native is None:
            return []
        return self._entities(
            self._native.region_query(
                float(bounds.left),
                float(bounds.top),
                float(bounds.right),
                float(bounds.bottom),
                mask & _FULL_MASK,
                self._slot_of(ignore_entity_id),
            )
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
        """Refuse: joints are not implemented by the Rapier backend yet.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError(
            f"{joint_type.name} joints are not implemented by the Rapier backend "
            f'yet; use physics.backend = "pymunk".'
        )

    def destroy_joint(self, joint_handle: Any) -> None:
        """Refuse: no joint can exist to destroy.

        Raises:
            NotImplementedError: Always.
        """
        raise NotImplementedError("The Rapier backend has no joints yet.")
