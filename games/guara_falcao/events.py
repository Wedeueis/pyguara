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
