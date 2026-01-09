"""Real-time event logging tool."""

import time
from collections import deque

from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import UIRenderer
from pyguara.common.types import Color, Vector2, Rect
from pyguara.events.dispatcher import EventDispatcher
from pyguara.tools.base import Tool

# Events to monitor
from pyguara.input.events import OnRawKeyEvent, OnActionEvent
from pyguara.events.lifecycle import QuitEvent


class EventMonitor(Tool):
    """Logs the last N events processed by the engine."""

    def __init__(self, container: DIContainer) -> None:
        """Initialize the event monitor."""
        super().__init__("event_monitor", container)
        self._dispatcher = container.get(EventDispatcher)
        self._log: deque[str] = deque(maxlen=20)
        self._panel_rect = Rect(10, 600, 400, 200)

        # Subscribe to interesting events
        self._dispatcher.subscribe(
            OnRawKeyEvent, self._on_key_down, filter_func=lambda e: e.is_down
        )
        self._dispatcher.subscribe(OnActionEvent, self._on_action)
        self._dispatcher.subscribe(QuitEvent, self._on_quit)
        # We omit MouseMotion to avoid spamming the log, or we could sample it

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
