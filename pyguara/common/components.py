"""ECS components shared by every subsystem.

Axis convention matches `pyguara.common.types`: Y increases downwards, so the
`up` direction is negative Y.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from pyguara.common.types import Vector2
from pyguara.ecs.component import BaseComponent


@dataclass(slots=True)
class Tag(BaseComponent):
    """A human-readable name for an entity, for debugging and editor display.

    Attributes:
        name: The display name.
    """

    name: str = "Entity"

    def __post_init__(self) -> None:
        """Initialise the BaseComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        BaseComponent.__init__(self)


@dataclass(slots=True)
class ResourceLink(BaseComponent):
    """Records the data resource an entity was built from.

    Attributes:
        resource_path: Path of the source resource.
    """

    resource_path: str

    def __post_init__(self) -> None:
        """Initialise the BaseComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        BaseComponent.__init__(self)


class Transform(BaseComponent):
    """Position, rotation and scale in 2D space, with optional parenting.

    A transform may be parented to another, in which case its stored values
    are local to that parent and the `world_*` properties resolve the chain.
    World values are cached and recomputed lazily: a setter marks the subtree
    dirty, and the next `world_*` read rebuilds only what it needs.

    Angles are in **radians** throughout, except `rotation_degrees`.

    Note:
        This component carries logic, which the data-only ECS rule otherwise
        forbids (hence `_allow_methods`). Moving the hierarchy math to a
        TransformSystem is tracked as cross-cutting concern CC-6; it touches
        most of the engine, so it is not attempted piecemeal.

    Attributes:
        interpolate: Opt in to fixed-timestep render interpolation.
        previous_position: Position at the previous fixed tick, maintained by
            `SceneManager.fixed_update()` when `interpolate` is set.
    """

    _allow_methods = True  # See the note above: hierarchy math lives here.

    def __init__(
        self,
        position: Vector2 | None = None,
        rotation: float = 0.0,
        scale: Vector2 | None = None,
        interpolate: bool = False,
    ) -> None:
        """Initialise an unparented transform.

        Args:
            position: Local position. Defaults to the origin.
            rotation: Local rotation in radians.
            scale: Local scale. Defaults to `(1, 1)`.
            interpolate: Opt in to fixed-timestep render interpolation.
        """
        super().__init__()

        # `is None`, not `or`: pymunk's Vec2d is falsy at (0, 0), so `scale or
        # default` silently rewrote an explicitly requested zero scale to (1, 1).
        self._local_position = position if position is not None else Vector2(0.0, 0.0)
        self._local_rotation = rotation
        self._local_scale = scale if scale is not None else Vector2(1.0, 1.0)

        self._parent: Transform | None = None
        self._children: list[Transform] = []

        # Cached world transform
        self._world_position: Vector2 = self._local_position
        self._world_rotation: float = self._local_rotation
        self._world_scale: Vector2 = self._local_scale
        self._is_dirty: bool = True

        # Fixed-timestep render interpolation (opt-in): when True,
        # SceneManager.fixed_update() snapshots previous_position once per
        # tick before any system moves this Transform, and Scene.render()'s
        # default combination lerps between it and the current position by
        # render_alpha instead of using the current position directly.
        self.interpolate = interpolate
        self.previous_position: Vector2 = self._local_position

    def render_position(self, alpha: float) -> Vector2:
        """Return where this transform should be drawn between two ticks.

        Physics advances at a fixed rate while frames are presented at the
        display's rate, so drawing `position` directly shows the last
        completed tick. When those rates are not locked together some frames
        show no movement and the next shows two ticks' worth -- motion that
        reads as stutter even though the simulation is perfectly regular.
        At 60Hz physics on a 75Hz display, a body moving 300 px/s is drawn
        in steps of 0 to 5 pixels where every step should be 4.

        Interpolating between the previous tick and the current one, by how
        far the frame sits between them, removes that. It costs one tick of
        latency, which is why it is opt-in through `interpolate`; a transform
        that has not opted in is drawn where it is, and `previous_position`
        is not maintained for it.

        Args:
            alpha: Progress through the current tick, 0.0 to 1.0. The
                application hands this to `Scene.render` as `render_alpha`.

        Returns:
            The position to draw at.
        """
        if not self.interpolate:
            return self.position
        return self.previous_position.lerp(self.position, alpha)

    # --- Properties ---

    @property
    def position(self) -> Vector2:
        """Get the local position."""
        return self._local_position

    @position.setter
    def position(self, value: Vector2) -> None:
        """Set the local position and mark hierarchy as dirty."""
        self._local_position = value
        self._mark_dirty()

    @property
    def rotation(self) -> float:
        """Get the local rotation in radians."""
        return self._local_rotation

    @rotation.setter
    def rotation(self, value: float) -> None:
        """Set the local rotation in radians and mark hierarchy as dirty."""
        self._local_rotation = float(value)
        self._mark_dirty()

    @property
    def rotation_degrees(self) -> float:
        """Get the local rotation in degrees."""
        return math.degrees(self._local_rotation)

    @rotation_degrees.setter
    def rotation_degrees(self, value: float) -> None:
        """Set the local rotation in degrees."""
        self._local_rotation = math.radians(value)
        self._mark_dirty()

    @property
    def scale(self) -> Vector2:
        """Get the local scale."""
        return self._local_scale

    @scale.setter
    def scale(self, value: Vector2) -> None:
        """Set the local scale and mark hierarchy as dirty."""
        self._local_scale = value
        self._mark_dirty()

    @property
    def world_position(self) -> Vector2:
        """Get the absolute world position."""
        self._update_world_transform()
        return self._world_position

    @world_position.setter
    def world_position(self, value: Vector2) -> None:
        """Set the absolute world position by adjusting local position."""
        if self._parent:
            self._parent._update_world_transform()
            # Convert world position to local space
            local_pos = self._parent.world_to_local(value)
            self.position = local_pos
        else:
            self.position = value

    @property
    def world_rotation(self) -> float:
        """Get the absolute world rotation in radians."""
        self._update_world_transform()
        return self._world_rotation

    @world_rotation.setter
    def world_rotation(self, value: float) -> None:
        """Set the absolute world rotation by adjusting local rotation."""
        if self._parent:
            self._parent._update_world_transform()
            parent_rot = self._parent.world_rotation
            self.rotation = value - parent_rot
        else:
            self.rotation = value

    @property
    def world_scale(self) -> Vector2:
        """Get the absolute world scale."""
        self._update_world_transform()
        return self._world_scale

    # --- Hierarchy Management ---

    @property
    def parent(self) -> Transform | None:
        """The parent transform, or None if this one is a root."""
        return self._parent

    def is_ancestor_of(self, other: Transform) -> bool:
        """Report whether this transform is somewhere above `other`.

        Args:
            other: The candidate descendant.

        Returns:
            True if `other` is this transform or below it in the hierarchy.
        """
        node: Transform | None = other
        while node is not None:
            if node is self:
                return True
            node = node._parent
        return False

    def set_parent(
        self, parent: Transform | None, keep_world_transform: bool = True
    ) -> None:
        """Attach this transform to a parent, or detach it with None.

        Args:
            parent: The new parent, or None to make this a root.
            keep_world_transform: Preserve the current world position,
                rotation and scale by rewriting the local values.

        Raises:
            ValueError: If `parent` is this transform or one of its own
                descendants. Such a cycle has no world transform, and every
                later `world_*` read would recurse until the stack ran out.
        """
        if parent is self._parent:
            return

        if parent is not None and self.is_ancestor_of(parent):
            raise ValueError(
                "Cannot parent a Transform to itself or to one of its own "
                "descendants; the resulting cycle has no world transform."
            )

        world_pos: Vector2 | None = None
        world_rot: float | None = None
        world_scl: Vector2 | None = None

        if keep_world_transform:
            world_pos = self.world_position
            world_rot = self.world_rotation
            world_scl = self.world_scale

        if self._parent and self in self._parent._children:
            self._parent._children.remove(self)

        self._parent = parent
        if parent:
            parent._children.append(self)

        if keep_world_transform and world_pos is not None:
            assert world_rot is not None
            assert world_scl is not None

            if parent:
                parent._update_world_transform()
                self.position = parent.world_to_local(world_pos)
                self.rotation = world_rot - parent.world_rotation

                # A zero-scaled parent has no invertible transform; leave the
                # local scale alone rather than dividing by zero.
                p_scale = parent.world_scale
                if p_scale.x != 0 and p_scale.y != 0:
                    self.scale = Vector2(
                        world_scl.x / p_scale.x, world_scl.y / p_scale.y
                    )
            else:
                self.position = world_pos
                self.rotation = world_rot
                self.scale = world_scl

        self._mark_dirty()

    @property
    def children(self) -> list[Transform]:
        """A snapshot copy of this transform's direct children."""
        return list(self._children)

    # --- Direction Vectors ---

    @property
    def right(self) -> Vector2:
        """The world-space right direction, `(1, 0)` at zero rotation."""
        return Vector2.right().rotated(self.world_rotation)

    @property
    def left(self) -> Vector2:
        """The world-space left direction, `(-1, 0)` at zero rotation."""
        return Vector2.left().rotated(self.world_rotation)

    @property
    def up(self) -> Vector2:
        """The world-space up direction, `(0, -1)` at zero rotation.

        Y increases downwards, so up is negative Y -- the same convention as
        `Vector2.up()`, which this used to contradict by returning `(0, 1)`.
        """
        return Vector2.up().rotated(self.world_rotation)

    @property
    def down(self) -> Vector2:
        """The world-space down direction, `(0, 1)` at zero rotation."""
        return Vector2.down().rotated(self.world_rotation)

    @property
    def forward(self) -> Vector2:
        """The facing direction; an alias for `right`.

        Zero rotation faces `(1, 0)`, and `look_at()` rotates to match.
        """
        return self.right

    # --- Operations ---

    def translate(self, translation: Vector2) -> None:
        """Move by an offset in local space.

        Args:
            translation: The offset to add to the local position.
        """
        self.position += translation

    def rotate(self, angle_radians: float) -> None:
        """Turn by an angle in **radians**.

        Args:
            angle_radians: The angle to add to the local rotation. Use
                `math.radians()` to convert, or set `rotation_degrees`.
        """
        self.rotation += angle_radians

    def look_at(self, target: Vector2) -> None:
        """Rotate so `forward` points at a world position.

        Args:
            target: The world point to face.
        """
        direction = target - self.world_position
        self.world_rotation = math.atan2(direction.y, direction.x)

    def distance_to(self, other: Transform) -> float:
        """Return the world-space distance to another transform.

        Args:
            other: The transform to measure to.

        Returns:
            The straight-line distance between world positions.
        """
        return self.world_position.distance_to(other.world_position)

    # --- Coordinate Conversion ---

    def local_to_world(self, local_point: Vector2) -> Vector2:
        """Convert a point from this transform's local space to world space.

        Args:
            local_point: The point in local space.

        Returns:
            The same point in world space.
        """
        self._update_world_transform()

        scaled = Vector2(
            local_point.x * self._world_scale.x, local_point.y * self._world_scale.y
        )
        rotated = scaled.rotated(self._world_rotation)
        return rotated + self._world_position

    def world_to_local(self, world_point: Vector2) -> Vector2:
        """Convert a point from world space to this transform's local space.

        Args:
            world_point: The point in world space.

        Returns:
            The same point in local space, or the origin if either world scale
            axis is zero, which makes the transform non-invertible.
        """
        self._update_world_transform()

        translated = world_point - self._world_position
        unrotated = translated.rotated(-self._world_rotation)
        if self._world_scale.x == 0 or self._world_scale.y == 0:
            return Vector2(0, 0)

        return Vector2(
            unrotated.x / self._world_scale.x, unrotated.y / self._world_scale.y
        )

    # --- Internal Updates ---

    def _mark_dirty(self) -> None:
        """Invalidate the cached world transform of this subtree.

        Stops at an already-dirty node. That is safe because cleaning a node
        also cleans all of its ancestors, so a dirty node can never have a
        clean descendant.
        """
        if not self._is_dirty:
            self._is_dirty = True
            for child in self._children:
                child._mark_dirty()

    def _update_world_transform(self) -> None:
        """Recompute the cached world transform if it is stale."""
        if not self._is_dirty:
            return

        if self._parent:
            self._parent._update_world_transform()

            scaled_pos = Vector2(
                self._local_position.x * self._parent._world_scale.x,
                self._local_position.y * self._parent._world_scale.y,
            )
            rotated_pos = scaled_pos.rotated(self._parent._world_rotation)

            self._world_position = self._parent._world_position + rotated_pos
            self._world_rotation = self._parent._world_rotation + self._local_rotation
            self._world_scale = Vector2(
                self._parent._world_scale.x * self._local_scale.x,
                self._parent._world_scale.y * self._local_scale.y,
            )
        else:
            self._world_position = self._local_position
            self._world_rotation = self._local_rotation
            self._world_scale = self._local_scale

        self._is_dirty = False

    def __repr__(self) -> str:
        """Return a debug representation with degrees for readability."""
        return (
            f"Transform(pos={self.position}, "
            f"rot={math.degrees(self.rotation):.1f}°, "
            f"scale={self.scale})"
        )
