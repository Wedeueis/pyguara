"""Module 3: Components.

Updated Sprite component to use a Texture resource.
"""

from dataclasses import dataclass
from pyguara.ecs.component import Component
from pyguara.common.types import Vector2
from pyguara.resources.types import Texture


@dataclass
class Transform(Component):
    """Stores position in world space."""

    position: Vector2


@dataclass
class Sprite(Component):
    """Visual representation using a loaded Texture."""

    texture: Texture
