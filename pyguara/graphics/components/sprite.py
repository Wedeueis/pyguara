"""Sprite component module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pyguara.common.types import Color, Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.resources.types import Texture

if TYPE_CHECKING:
    pass


@dataclass
class Sprite(BaseComponent):
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

    # Optional material for custom shaders/effects (None = default sprite shader)
    material: Any = None  # Type: Optional["Material"]

    # Multiplied into the texture at draw time. Opaque white (the default)
    # draws unmodified, and a batch of nothing but white sprites is marked
    # untinted so a backend can skip the work -- see
    # RenderBatch.colors_enabled. What "the work" is differs: Pygame tints
    # a copied surface per sprite, while the GL path carries the colour as
    # a per-instance vertex attribute it packs either way.
    color: Color = field(default_factory=lambda: Color(255, 255, 255, 255))

    def __post_init__(self) -> None:
        """Initialize the BaseComponent portion (entity backref)."""
        super().__init__()
