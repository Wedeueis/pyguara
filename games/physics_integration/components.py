"""Module 5: Components."""

from dataclasses import dataclass
from pyguara.ecs.component import Component
from pyguara.common.types import Vector2, Color


@dataclass
class BoxSprite(Component):
    """Simple box visualization."""

    color: Color
    size: Vector2
