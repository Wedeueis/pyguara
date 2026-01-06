"""ECS components for physics."""

from dataclasses import dataclass, field
from typing import List, Optional

from pyguara.common.types import Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.physics.types import CollisionLayer, PhysicsMaterial, ShapeType, BodyType
from pyguara.physics.protocols import IPhysicsBody


@dataclass
class Collider(BaseComponent):
    """
    Component defining the collision shape.

    Attributes:
        shape_type: Geometric shape.
        dimensions: Dimensions [radius] for circle, or [width, height] for box.
        offset: Local offset from the RigidBody center.
    """

    shape_type: ShapeType = ShapeType.BOX
    dimensions: List[float] = field(default_factory=lambda: [32.0, 32.0])
    offset: Vector2 = field(default_factory=lambda: Vector2(0, 0))
    material: PhysicsMaterial = field(default_factory=PhysicsMaterial)
    layer: CollisionLayer = field(default_factory=CollisionLayer)
    is_sensor: bool = False

    def __post_init__(self) -> None:
        """Initialize base component state."""
        super().__init__()


@dataclass
class RigidBody(BaseComponent):
    """
    Component representing a physical object.

    Attributes:
        mass: The mass of the body (default 1.0).
        body_type: Static, Dynamic, or Kinematic.
        fixed_rotation: If True, physics won't rotate the object.
        gravity_scale: Scale factor for gravity applied to this body.
    """

    # Dataclass fields
    mass: float = 1.0
    body_type: BodyType = BodyType.DYNAMIC
    fixed_rotation: bool = False
    gravity_scale: float = 1.0

    # Internal handle (injected by system)
    _body_handle: Optional[IPhysicsBody] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Initialize base component state."""
        super().__init__()

    @property
    def handle(self) -> Optional[IPhysicsBody]:
        """Access the underlying physics body interface."""
        return self._body_handle
