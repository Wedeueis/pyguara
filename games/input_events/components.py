"""Module 4: Components."""

from dataclasses import dataclass

from pyguara.common.types import Color, Vector2
from pyguara.ecs.component import Component


@dataclass
class Transform(Component):
    """Stores position in world space."""

    position: Vector2


@dataclass
class Movement(Component):
    """What the player is currently asking this entity to do.

    Written by `InputBridgeSystem` from action events, read by
    `PlayerSystem`. Holding the *intent* rather than a velocity is what
    keeps this module about input: nothing here integrates or simulates
    anything, and module 5 (`physics_integration`) is the first place a
    body actually moves under forces.

    Attributes:
        direction: Unit-ish direction the player is holding, (0, 0) when
            nothing is held.
        speed: Pixels per second while a direction is held.
    """

    direction: Vector2
    speed: float


@dataclass
class Sprite(Component):
    """Simple visual representation."""

    color: Color
    size: Vector2
