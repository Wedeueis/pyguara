"""Guará & Falcão - Game Events.

Custom events for platformer game logic.
"""

from dataclasses import dataclass

from pyguara.common.types import Vector2


@dataclass
class PlayerLandedEvent:
    """Fired when player lands on ground."""

    position: Vector2


@dataclass
class PlayerJumpedEvent:
    """Fired when player jumps."""

    is_wall_jump: bool = False


@dataclass
class PlayerDamagedEvent:
    """Fired when player takes damage."""

    damage: int
    remaining_health: int


@dataclass
class PlayerDeathEvent:
    """Fired when player dies."""

    pass


@dataclass
class CollectiblePickedEvent:
    """Fired when player picks up a collectible."""

    collect_type: str
    value: int


@dataclass
class CheckpointReachedEvent:
    """Fired when player reaches a checkpoint."""

    zone_name: str
    spawn_point: Vector2


@dataclass
class LevelCompleteEvent:
    """Fired when player completes the level."""

    score: int
    coins: int


@dataclass
class DebugCollidersToggled:
    """Fired when the options panel turns collider outlines on or off.

    An event rather than a direct call: the options panel is a scene
    pushed over the game and holds no reference to it, and reaching down
    the scene stack to find one would couple a menu to what it was opened
    from.
    """

    shown: bool
