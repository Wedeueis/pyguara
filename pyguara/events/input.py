"""Input events for keyboard and mouse interactions."""

from dataclasses import dataclass
import time
from typing import Any


@dataclass
class KeyboardEvent:
    """Base class for key interactions."""

    key_code: int  # The integer scan code (e.g., pygame.K_SPACE)
    timestamp: float = 0.0
    source: Any = None

    def __post_init__(self) -> None:
        """Initialize timestamp if not provided."""
        if self.timestamp == 0.0:
            self.timestamp = time.time()


@dataclass
class KeyDownEvent(KeyboardEvent):
    """Fired when a key is pressed."""

    pass


@dataclass
class KeyUpEvent(KeyboardEvent):
    """Fired when a key is released."""

    pass


@dataclass
class MouseMotionEvent:
    """Fired when the mouse moves."""

    x: int
    y: int
    rel_x: int
    rel_y: int
    timestamp: float = 0.0
    source: Any = None

    def __post_init__(self) -> None:
        """Initialize timestamp if not provided."""
        if self.timestamp == 0.0:
            self.timestamp = time.time()
