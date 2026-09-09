"""Keyboard and mouse input events.

These are the engine's backend-neutral input events. A window backend
translates its native events (SDL, via pygame) into these in `poll_events()`,
so nothing above the backend boundary imports pygame or reads its constants
(issue #9). Key codes are still SDL values -- the same integers
`pyguara.input.keys` names.

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
        key_code: SDL key code for the key (see `pyguara.input.keys`).
        modifiers: The shift/ctrl/alt flags held when the event fired, as
            SDL `KMOD_*` values.
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    key_code: int
    modifiers: set[int] = field(default_factory=set)
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class KeyDownEvent(KeyboardEvent):
    """Fired when a key is pressed."""


@dataclass
class KeyUpEvent(KeyboardEvent):
    """Fired when a key is released."""


@dataclass
class MouseButtonEvent:
    """Fired when a mouse button is pressed or released.

    Attributes:
        button: Button index (1 left, 2 middle, 3 right, 4/5 wheel).
        x: Cursor X position in window pixels.
        y: Cursor Y position in window pixels.
        is_down: True on press, False on release.
        modifiers: The shift/ctrl/alt flags held when the event fired.
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    button: int
    x: int
    y: int
    is_down: bool
    modifiers: set[int] = field(default_factory=set)
    timestamp: float = field(default_factory=time.time)
    source: Any = None

    @property
    def pos(self) -> tuple[int, int]:
        """The cursor position as an ``(x, y)`` tuple."""
        return (self.x, self.y)


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

    @property
    def pos(self) -> tuple[int, int]:
        """The cursor position as an ``(x, y)`` tuple."""
        return (self.x, self.y)
