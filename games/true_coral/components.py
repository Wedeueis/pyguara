"""True Coral - ECS Components.

Pure data containers for the puzzle game.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Tuple

from pyguara.ecs.component import BaseComponent
from pyguara.common.types import Vector2, Color


class BlockType(Enum):
    """Types of blocks in the puzzle."""

    PLAYER = auto()
    CRATE = auto()
    WALL = auto()
    GOAL = auto()
    FLOOR = auto()


@dataclass
class GridPosition(BaseComponent):
    """Integer grid coordinates for puzzle entities."""

    x: int = 0
    y: int = 0

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()

    def to_tuple(self) -> Tuple[int, int]:
        """Return position as tuple."""
        return (self.x, self.y)


@dataclass
class Block(BaseComponent):
    """Block type marker component."""

    block_type: BlockType = BlockType.FLOOR

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class Pushable(BaseComponent):
    """Marker for entities that can be pushed (crates)."""

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class MoveHistory(BaseComponent):
    """Stores move history for undo functionality."""

    history: List[Tuple[int, int, int, int]] = field(default_factory=list)
    # Each entry: (player_from_x, player_from_y, crate_from_x, crate_from_y)
    # If no crate moved, crate coords are -1, -1

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()

    def push(
        self, player_from: Tuple[int, int], crate_from: Tuple[int, int] = (-1, -1)
    ) -> None:
        """Record a move."""
        self.history.append(
            (player_from[0], player_from[1], crate_from[0], crate_from[1])
        )

    def pop(self) -> Tuple[Tuple[int, int], Tuple[int, int]] | None:
        """Retrieve and remove the last move."""
        if not self.history:
            return None
        entry = self.history.pop()
        return ((entry[0], entry[1]), (entry[2], entry[3]))


@dataclass
class Moving(BaseComponent):
    """Marker for entities currently being animated."""

    from_pos: Vector2 = field(default_factory=Vector2.zero)
    to_pos: Vector2 = field(default_factory=Vector2.zero)
    progress: float = 0.0

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class LevelState(BaseComponent):
    """Stores the current level state."""

    level_index: int = 0
    total_moves: int = 0
    is_complete: bool = False

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class GridSprite(BaseComponent):
    """Visual representation for grid entities."""

    color: Color = field(default_factory=lambda: Color(255, 255, 255))
    size: Vector2 = field(default_factory=lambda: Vector2(48, 48))
    is_floor: bool = False

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()
