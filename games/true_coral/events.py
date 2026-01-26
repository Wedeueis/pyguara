"""True Coral - Game Events.

Custom events for puzzle game logic.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class BlockMoveEvent:
    """Fired when a block moves from one grid cell to another."""

    entity_id: str
    from_pos: Tuple[int, int]
    to_pos: Tuple[int, int]


@dataclass
class PlayerMoveEvent:
    """Fired when the player attempts to move."""

    direction: Tuple[int, int]  # (dx, dy)


@dataclass
class LevelCompleteEvent:
    """Fired when all crates are on goals."""

    level_index: int
    total_moves: int


@dataclass
class UndoEvent:
    """Fired when player requests undo."""

    pass


@dataclass
class RestartLevelEvent:
    """Fired when player requests level restart."""

    pass


@dataclass
class NextLevelEvent:
    """Fired to advance to the next level."""

    pass
