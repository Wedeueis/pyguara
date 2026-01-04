"""
Defines the Viewport logic for screen-space rendering management.

This module provides the `Viewport` class, which defines the specific rectangular
region of the OS window where the game world is drawn. While the `Camera` controls
*what* you see (World Space), the `Viewport` controls *where* it appears on
the screen (Screen Space).

This is essential for:
1.  Split-screen multiplayer (two viewports side-by-side).
2.  Minimaps (a small viewport in the corner).
3.  Maintaing strict aspect ratios (adding black bars/letterboxing automatically).
"""

from __future__ import annotations

from pyguara.common.types import Rect, Vector2


class Viewport(Rect):
    """
    Represents the drawing area on the screen.

    Inherits from `pyguara.common.types.Rect` (and thus `pygame.Rect`), so it
    can be passed directly to `pygame.draw` functions or used for clipping.

    Attributes:
        x (int): The left X coordinate on the window.
        y (int): The top Y coordinate on the window.
        width (int): The width of the drawing area.
        height (int): The height of the drawing area.
    """

    def __init__(self, x: int, y: int, width: int, height: int):
        """
        Initialize a new Viewport.

        Args:
            x (int): X position on the window.
            y (int): Y position on the window.
            width (int): Width in pixels.
            height (int): Height in pixels.
        """
        super().__init__(x, y, width, height)

    @property
    def aspect_ratio(self) -> float:
        """
        Get the aspect ratio (width / height) of this viewport.

        Returns:
            float: The aspect ratio. Returns 0.0 if height is 0.
        """
        return float(self.width / self.height) if self.height != 0 else 0.0

    @property
    def center_vec(self) -> Vector2:
        """
        Get the center point of the viewport as a Vector2.

        Useful for the RenderPipeline to calculate camera offsets relative
        to the viewport center rather than the window center.

        Returns:
            Vector2: (center_x, center_y)
        """
        return Vector2(self.centerx, self.centery)

    def get_relative_mouse_pos(self, global_mouse_pos: Vector2) -> Vector2:
        """
        Convert global window mouse coordinates to viewport-relative coordinates.

        If your viewport has a top-left offset (e.g., in split-screen or
        due to black bars), a mouse click at (100, 100) on the window might
        actually be (0, 0) inside this viewport.

        Args:
            global_mouse_pos (Vector2): The raw mouse position from the OS/Pygame.

        Returns:
            Vector2: The mouse position relative to this viewport's (0,0).
        """
        return Vector2(global_mouse_pos.x - self.x, global_mouse_pos.y - self.y)

    def contains_mouse(self, global_mouse_pos: Vector2) -> bool:
        """
        Check if the mouse is currently hovering over this viewport.

        Essential for split-screen games to know which player/camera should
        receive input.

        Args:
            global_mouse_pos (Vector2): The raw mouse position.

        Returns:
            bool: True if the mouse is inside this viewport.
        """
        return bool(self.collidepoint(global_mouse_pos.x, global_mouse_pos.y))

    @staticmethod
    def create_fullscreen(window_width: int, window_height: int) -> Viewport:
        """
        Create a viewport that covers the entire window.

        Args:
            window_width (int): Window width.
            window_height (int): Window height.

        Returns:
            Viewport: A viewport starting at (0,0) with full dimensions.
        """
        return Viewport(0, 0, window_width, window_height)

    @staticmethod
    def create_best_fit(
        window_width: int, window_height: int, target_aspect_ratio: float
    ) -> Viewport:
        """
        Create a viewport that maintains a target aspect ratio within the window.

        This automatically calculates the size and position for "Letterboxing"
        (black bars top/bottom) or "Pillarboxing" (black bars left/right).

        Args:
            window_width (int): Current window width.
            window_height (int): Current window height.
            target_aspect_ratio (float): Desired ratio (e.g., 16/9 or 1.77).

        Returns:
            Viewport: A centered viewport fitting the target ratio.
        """
        window_ratio = window_width / window_height if window_height != 0 else 0

        if window_ratio > target_aspect_ratio:
            # Window is too wide (Pillarbox): Fit by height
            new_height = window_height
            new_width = int(new_height * target_aspect_ratio)
            offset_x = (window_width - new_width) // 2
            offset_y = 0
        else:
            # Window is too tall (Letterbox): Fit by width
            new_width = window_width
            new_height = int(new_width / target_aspect_ratio)
            offset_x = 0
            offset_y = (window_height - new_height) // 2

        return Viewport(offset_x, offset_y, new_width, new_height)
