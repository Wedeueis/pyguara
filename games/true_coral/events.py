"""True Coral - Game Events.

Custom events for snake game logic. Every event carries `timestamp`/
`source` so it structurally satisfies `pyguara.events.protocols.Event` --
`protocolo_bandeira` shipped without these and every dispatch()/subscribe()
call site was quietly type-incorrect until a follow-up fix (#128).
"""

import time
from dataclasses import dataclass, field
from typing import Any

from pyguara.common.grid import Cell


@dataclass
class FoodEatenEvent:
    """Fired when the snake's head lands on a food cell."""

    food_type: str
    cell: Cell
    points: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class SnakeDiedEvent:
    """Fired when the snake hits a wall or itself and loses a life."""

    cause: str  # "wall" or "self"
    lives_remaining: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class GameOverEvent:
    """Fired when the snake's lives reach zero."""

    final_score: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class StarEffectStarted:
    """Fired when `StarEffect` is applied -- the cue to start the rain overlay."""

    entity_id: str
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class StarEffectEnded:
    """Fired when `StarEffect` expires -- the cue to stop the rain overlay."""

    entity_id: str
    timestamp: float = field(default_factory=time.time)
    source: Any = None
