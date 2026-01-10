"""Common ECS components used across the engine."""

import math
from typing import List, Optional
from dataclasses import dataclass

from pyguara.common.types import Vector2
from pyguara.ecs.component import BaseComponent


@dataclass
class Tag(BaseComponent):
    """Component for labeling entities with a human-readable name."""

    name: str = "Entity"

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class ResourceLink(BaseComponent):
    """Component that links an entity/component to its source DataResource."""

    resource_path: str

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


class Transform(BaseComponent):
    """Component representing position, rotation, and scale in 2D space."""

    def __init__(
        self,
        position: Optional[Vector2] = None,
        rotation: float = 0.0,
        scale: Optional[Vector2] = None,
    ) -> None:
        """Initialize the transform."""
        super().__init__()  # Initialize BaseComponent (sets self.entity = None)

        self._local_position = position or Vector2(0.0, 0.0)
        self._local_rotation = rotation
        self._local_scale = scale or Vector2(1.0, 1.0)

        # Hierarchy
        self._parent: Optional["Transform"] = None
        self._children: List["Transform"] = []

        # Cached world transform
        self._world_position: Vector2 = self._local_position
        self._world_rotation: float = self._local_rotation
        self._world_scale: Vector2 = self._local_scale
        self._is_dirty: bool = True

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
    def parent(self) -> Optional["Transform"]:
        """Get the parent transform."""
        return self._parent

    def set_parent(
        self, parent: Optional["Transform"], keep_world_transform: bool = True
    ) -> None:
        """Set the parent transform."""
        if parent == self._parent:
            return

        # Store current world state if we need to maintain it
        world_pos: Optional[Vector2] = None
        world_rot: Optional[float] = None
        world_scl: Optional[Vector2] = None

        if keep_world_transform:
            world_pos = self.world_position
            world_rot = self.world_rotation
            world_scl = self.world_scale

        # Remove from old parent
        if self._parent:
            if self in self._parent._children:
                self._parent._children.remove(self)

        # Attach to new parent
        self._parent = parent
        if parent:
            parent._children.append(self)

        # Restore world state relative to new parent
        if keep_world_transform and world_pos is not None:
            assert world_rot is not None
            assert world_scl is not None

            if parent:
                parent._update_world_transform()
                self.position = parent.world_to_local(world_pos)
                self.rotation = world_rot - parent.world_rotation

                # Scale logic
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
    def children(self) -> List["Transform"]:
        """Get a copy of the list of children."""
        return list(self._children)

    # --- Direction Vectors ---

    @property
    def right(self) -> Vector2:
        """Get the world-space Right direction vector."""
        return Vector2(1, 0).rotated(self.world_rotation)

    @property
    def up(self) -> Vector2:
        """Get the world-space Up direction vector."""
        return Vector2(0, 1).rotated(self.world_rotation)

    @property
    def forward(self) -> Vector2:
        """Get the forward vector."""
        return self.right

    # --- Operations ---

    def translate(self, translation: Vector2) -> None:
        """Move the transform by the given vector in local space."""
        self.position += translation

    def rotate(self, angle: float) -> None:
        """Rotate the transform by the given angle in radians."""
        self.rotation += angle

    def look_at(self, target: Vector2) -> None:
        """Rotate the transform to face a target world position."""
        direction = target - self.world_position
        self.world_rotation = math.atan2(direction.y, direction.x)

    def distance_to(self, other: "Transform") -> float:
        """Calculate distance to another transform."""
        return self.world_position.distance_to(other.world_position)

    # --- Coordinate Conversion ---

    def local_to_world(self, local_point: Vector2) -> Vector2:
        """Transform a point from local space to world space."""
        self._update_world_transform()

        # Scale
        scaled = Vector2(
            local_point.x * self._world_scale.x, local_point.y * self._world_scale.y
        )
        # Rotate
        rotated = scaled.rotated(self._world_rotation)
        # Translate
        return rotated + self._world_position

    def world_to_local(self, world_point: Vector2) -> Vector2:
        """Transform a point from world space to local space."""
        self._update_world_transform()

        # Inverse Translate
        translated = world_point - self._world_position
        # Inverse Rotate
        unrotated = translated.rotated(-self._world_rotation)
        # Inverse Scale
        if self._world_scale.x == 0 or self._world_scale.y == 0:
            return Vector2(0, 0)

        return Vector2(
            unrotated.x / self._world_scale.x, unrotated.y / self._world_scale.y
        )

    # --- Internal Updates ---

    def _mark_dirty(self) -> None:
        """Mark this transform and all children as dirty."""
        if not self._is_dirty:
            self._is_dirty = True
            for child in self._children:
                child._mark_dirty()

    def _update_world_transform(self) -> None:
        """Recalculate world transform if dirty."""
        if not self._is_dirty:
            return

        if self._parent:
            self._parent._update_world_transform()

            # Apply parent transform
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
        """Return string representation of the transform."""
        return (
            f"Transform(pos={self.position}, "
            f"rot={math.degrees(self.rotation):.1f}°, "
            f"scale={self.scale})"
        )
