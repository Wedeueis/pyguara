"""Real-time event logging tool."""

import time
from collections import deque
from typing import Any

from pyguara.common.types import Color, Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.lifecycle import QuitEvent
from pyguara.graphics.protocols import UIRenderer

# Events to monitor
from pyguara.input.events import OnActionEvent, OnRawKeyEvent
from pyguara.tools.base import Tool


class EventMonitor(Tool):
    """Logs the last N events processed by the engine."""

    def __init__(self, container: DIContainer) -> None:
        """Initialize the event monitor."""
        super().__init__("event_monitor", container)
        self._dispatcher = container.get(EventDispatcher)
        self._log: deque[str] = deque(maxlen=20)
        self._panel_rect = Rect(10, 600, 400, 200)

        # Subscribe to interesting events. The (type, handler) pairs are kept
        # so on_removed() can undo every one -- an EventMonitor that is
        # unregistered must stop receiving events, not keep appending to a
        # log nobody renders. (MouseMotion omitted to avoid spamming.)
        self._subscriptions: list[tuple[type, Any]] = [
            (OnRawKeyEvent, self._on_key_down),
            (OnActionEvent, self._on_action),
            (QuitEvent, self._on_quit),
        ]
        self._dispatcher.subscribe(
            OnRawKeyEvent, self._on_key_down, filter_func=lambda e: e.is_down
        )
        self._dispatcher.subscribe(OnActionEvent, self._on_action)
        self._dispatcher.subscribe(QuitEvent, self._on_quit)

    def on_removed(self) -> None:
        """Drop every dispatcher subscription this monitor made."""
        for event_type, handler in self._subscriptions:
            self._dispatcher.unsubscribe(event_type, handler)
        self._subscriptions.clear()

    def _log_msg(self, category: str, msg: str) -> None:
        """Add a formatted message to the log.

        Args:
            category: Event category (e.g., INPUT).
            msg: The detail message.
        """
        timestamp = time.strftime("%H:%M:%S")
        self._log.append(f"[{timestamp}] [{category}] {msg}")

    def _on_key_down(self, event: OnRawKeyEvent) -> None:
        self._log_msg("KEY", f"Down: {event.key_code}")

    def _on_action(self, event: OnActionEvent) -> None:
        self._log_msg("ACTION", f"{event.action_name} ({event.value})")

    def _on_quit(self, event: QuitEvent) -> None:
        self._log_msg("SYSTEM", "Quit Requested")

    def update(self, dt: float) -> None:
        """No update logic needed."""
        pass

    def render(self, renderer: UIRenderer) -> None:
        """Render the event log console.

        Args:
            renderer: UI Backend.
        """
        # Background
        renderer.draw_rect(self._panel_rect, Color(20, 20, 20, 200), 0)
        renderer.draw_rect(self._panel_rect, Color(100, 200, 100), 2)

        # Title
        renderer.draw_text(
            "Event Monitor",
            Vector2(self._panel_rect.x + 10, self._panel_rect.y + 10),
            Color(100, 200, 100),
            18,
        )

        # Log Lines
        x = self._panel_rect.x + 10
        y = self._panel_rect.y + 35

        # Draw newest last
        for line in self._log:
            renderer.draw_text(line, Vector2(x, y), Color(200, 200, 200), 14)
            y += 16
