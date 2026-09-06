"""Module 5: Components."""

from dataclasses import dataclass

from pyguara.common.types import Color, Vector2
from pyguara.ecs.component import Component


@dataclass
class BoxSprite(Component):
    """Simple box visualization."""

    color: Color
    size: Vector2
