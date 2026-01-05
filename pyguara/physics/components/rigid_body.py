"""ECS components for physics."""

from dataclasses import dataclass, field
from typing import Optional

from pyguara.physics.types import BodyType
from pyguara.physics.protocols import IPhysicsBody


@dataclass
class RigidBody:
    """
    Component representing a physical object.

    Attributes:
        body_type: Static, Dynamic, or Kinematic.
        fixed_rotation: If True, physics won't rotate the object.
        _body_handle: Internal reference to the backend body.
    """

    body_type: BodyType = BodyType.DYNAMIC
    fixed_rotation: bool = False
    gravity_scale: float = 1.0

    # Runtime handle (injected by system)
    _body_handle: Optional[IPhysicsBody] = field(default=None, repr=False)

    @property
    def handle(self) -> Optional[IPhysicsBody]:
        """Access the underlying physics body interface."""
        return self._body_handle
