"""Sprite component module."""

from dataclasses import dataclass
from pyguara.resources.types import Texture


@dataclass
class Sprite:
    """A visual component representing a 2D image in the world."""

    texture: Texture
    layer: int = 0  # 0=Background, 10=Main, 100=UI
    z_index: int = 0  # For sorting within the same layer (Y-Sort)
    visible: bool = True
    flip_x: bool = False
    flip_y: bool = False

    # Batching optimization hint
    is_static: bool = False
