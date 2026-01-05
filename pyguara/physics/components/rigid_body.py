"""ECS components for physics."""

from dataclasses import dataclass, field
from typing import Optional

from pyguara.ecs.component import BaseComponent
from pyguara.physics.types import BodyType
from pyguara.physics.protocols import IPhysicsBody


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
