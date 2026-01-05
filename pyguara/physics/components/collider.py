"""ECS components for physics."""

from dataclasses import dataclass, field
from typing import List

from pyguara.common.types import Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.physics.types import CollisionLayer, PhysicsMaterial, ShapeType


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
