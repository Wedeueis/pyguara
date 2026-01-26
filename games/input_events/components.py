"""Module 4: Components."""

from dataclasses import dataclass
from pyguara.ecs.component import Component
from pyguara.common.types import Vector2, Color


@dataclass
class Transform(Component):
    """Stores position in world space."""

    position: Vector2


@dataclass
class Velocity(Component):
    """Stores velocity vector."""

    value: Vector2


@dataclass
class Sprite(Component):
    """Simple visual representation."""

    color: Color
    size: Vector2
