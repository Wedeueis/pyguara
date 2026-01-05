"""Interfaces for physics engine adapters."""

from typing import Any, List, Optional, Protocol, Union

from pyguara.common.types import Vector2
from pyguara.physics.types import (
    BodyType,
    CollisionLayer,
    PhysicsMaterial,
    RaycastHit,
    ShapeType,
)


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

    def apply_force(self, force: Vector2, point: Optional[Vector2] = None) -> None:
        """Apply a continuous force to the body."""
        ...

    def apply_impulse(self, impulse: Vector2, point: Optional[Vector2] = None) -> None:
        """Apply an instant impulse to the body."""
        ...


class IPhysicsEngine(Protocol):
    """Interface for the core physics simulation engine."""

    def initialize(self, gravity: Vector2) -> None:
        """Initialize the physics world."""
        ...

    def update(self, delta_time: float) -> None:
        """Step the simulation forward."""
        ...

    def create_body(
        self, entity_id: Union[int, str], body_type: BodyType, position: Vector2
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
        dimensions: List[float],
        offset: Vector2,
        material: PhysicsMaterial,
        collision_layer: CollisionLayer,
        is_sensor: bool,
    ) -> Any:
        """Attach a collision shape to a body."""
        ...

    def raycast(
        self, start: Vector2, end: Vector2, mask: int = 0xFFFFFFFF
    ) -> Optional[RaycastHit]:
        """Cast a ray in the physics world."""
        ...
