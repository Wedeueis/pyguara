"""Keyboard and mouse input events.

`KeyDownEvent` and `KeyUpEvent` share the `KeyboardEvent` base, so a handler
subscribed to `KeyboardEvent` receives both -- see `EventDispatcher.dispatch`.
"""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class KeyboardEvent:
    """Base for key press and release events.

    Attributes:
        key_code: Backend scan code for the key, e.g. `pygame.K_SPACE`.
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    key_code: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class KeyDownEvent(KeyboardEvent):
    """Fired when a key is pressed."""


@dataclass
class KeyUpEvent(KeyboardEvent):
    """Fired when a key is released."""


@dataclass
class MouseMotionEvent:
    """Fired when the mouse moves.

    Attributes:
        x: Cursor X position in window pixels.
        y: Cursor Y position in window pixels.
        rel_x: Horizontal movement since the previous motion event.
        rel_y: Vertical movement since the previous motion event.
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    x: int
    y: int
    rel_x: int
    rel_y: int
    timestamp: float = field(default_factory=time.time)
    source: Any = None
