"""Event system: the dispatcher, its contracts, and the engine's own events.

Subscription is by type and matches subclasses, so subscribing to
`KeyboardEvent` receives both `KeyDownEvent` and `KeyUpEvent`.
"""

from pyguara.events.dispatcher import EventDispatcher, HandlerRecord
from pyguara.events.input import (
    KeyboardEvent,
    KeyDownEvent,
    KeyUpEvent,
    MouseMotionEvent,
)
from pyguara.events.lifecycle import ApplicationStartEvent, QuitEvent
from pyguara.events.protocols import Event, IEventDispatcher
from pyguara.events.types import ErrorHandlingStrategy, EventHandler
from pyguara.events.window import WindowResizeEvent

__all__ = [
    "ApplicationStartEvent",
    "ErrorHandlingStrategy",
    "Event",
    "EventDispatcher",
    "EventHandler",
    "HandlerRecord",
    "IEventDispatcher",
    "KeyDownEvent",
    "KeyUpEvent",
    "KeyboardEvent",
    "MouseMotionEvent",
    "QuitEvent",
    "WindowResizeEvent",
]
