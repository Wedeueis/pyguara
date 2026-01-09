"""Performance monitoring tool implementation."""

import pygame
from collections import deque

from pyguara.di.container import DIContainer
from pyguara.graphics.protocols import UIRenderer
from pyguara.tools.base import Tool
from pyguara.common.types import Color, Rect, Vector2


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
        self._clock = pygame.time.Clock()
        self._fps_history: deque[float] = deque(maxlen=60)
        self._avg_fps = 0.0

    def update(self, dt: float) -> None:
        """Calculate FPS statistics.

        Args:
            dt: Delta time.
        """
        # Note: In a real app, you'd get the actual clock from the container
        # This is just an estimation for the tool's update cycle
        current_fps = 1.0 / dt if dt > 0 else 0.0
        self._fps_history.append(current_fps)
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
