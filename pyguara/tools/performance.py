"""Performance monitoring tool implementation."""

from collections import deque

from pyguara.common.types import Color, Rect, Vector2
from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import UIRenderer
from pyguara.tools.base import Tool


class PerformanceMonitor(Tool):
    """Tracks and displays real-time engine statistics.

    Monitors FPS and other vital metrics.
    """

    def __init__(self, container: DIContainer) -> None:
        """Initialize the performance monitor.

        Args:
            container: The DI container.
        """
        super().__init__("performance_monitor", container)
        self._fps_history: deque[float] = deque(maxlen=60)
        self._avg_fps = 0.0

    def update(self, dt: float) -> None:
        """Fold this frame's duration into the rolling FPS average.

        Args:
            dt: Delta time in seconds.
        """
        # A non-positive dt (first frame, a pause, a clock that went
        # backwards) has no meaningful FPS -- skip it rather than feeding a
        # 0.0 sample that would drag the average down for a full second.
        if dt <= 0:
            return
        self._fps_history.append(1.0 / dt)
        self._avg_fps = sum(self._fps_history) / len(self._fps_history)

    def render(self, renderer: UIRenderer) -> None:
        """Draw the performance panel.

        Args:
            renderer: The UI renderer.
        """
        # Draw Background
        bg_rect = Rect(10, 10, 150, 60)
        renderer.draw_rect(bg_rect, Color(0, 0, 0), 0)  # Fill
        renderer.draw_rect(bg_rect, Color(100, 255, 100), 2)  # Border

        # Draw FPS Text
        color = Color(100, 255, 100)
        if self._avg_fps < 30:
            color = Color(255, 50, 50)

        renderer.draw_text(
            f"FPS: {int(self._avg_fps)}", Vector2(20, 20), color, size=20
        )
