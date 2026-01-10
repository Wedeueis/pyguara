"""Sprite component module."""

from dataclasses import dataclass, field
from pyguara.resources.types import Texture
from pyguara.common.types import Vector2


@dataclass
class Sprite:
    """A visual component representing a 2D image in the world.

    Implements the Renderable protocol, allowing it to be submitted directly
    to the RenderSystem. The position can be:
    - Absolute world position for standalone sprites
    - Relative offset when attached to an entity with Transform
    - Combined with entity Transform for final rendering position
    """

    texture: Texture
    layer: int = 0  # 0=Background, 10=Main, 100=UI
    z_index: int = 0  # For sorting within the same layer (Y-Sort)
    visible: bool = True
    flip_x: bool = False
    flip_y: bool = False

    # Batching optimization hint
    is_static: bool = False

    # Protocol compliance for Renderable (required for rendering)
    position: Vector2 = field(default_factory=Vector2.zero)  # Position or offset
    rotation: float = 0.0  # Rotation in degrees
    scale: Vector2 = field(default_factory=lambda: Vector2(1, 1))
