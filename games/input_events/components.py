"""Module 4: Components."""

from dataclasses import dataclass

from pyguara.common.types import Color, Vector2
from pyguara.ecs.component import Component


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
