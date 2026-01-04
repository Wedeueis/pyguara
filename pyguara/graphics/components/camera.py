"""
Defines the Camera component for 2D coordinate transformations.

This module provides the `Camera2D` class, which is responsible for converting
coordinates between World Space (game logic) and Screen Space (pixels).
It serves as a data container used by the RenderPipeline, decoupling the math
of "viewing" from the logic of "drawing".
"""

from __future__ import annotations
from typing import cast

from pyguara.common.types import Vector2, Rect


class Camera2D:
    """
    A 2D Camera component that defines the viewable area of the game world.

    It handles Zoom, Rotation, and Panning math. It does NOT render anything;
    it simply provides the transformation matrices (or equivalent logic) for the renderer.

    Attributes:
        position (Vector2): The center of the camera in World Coordinates.
        offset (Vector2): The center of the viewport in Screen Coordinates.
        zoom (float): The scale factor (1.0 = 100%, 2.0 = 200%).
        rotation (float): The rotation in degrees.
    """

    def __init__(self, width: int, height: int):
        """
        Initialize the Camera with a default viewport size.

        Args:
            width (int): The initial width of the target viewport/screen.
            height (int): The initial height of the target viewport/screen.
        """
        self.position: Vector2 = Vector2.zero()
        self.offset: Vector2 = Vector2(width / 2, height / 2)
        self.zoom: float = 1.0
        self.rotation: float = 0.0

    def set_viewport_size(self, width: int, height: int) -> None:
        """
        Recalculate the screen offset based on new dimensions.

        Call this when the window is resized to keep the camera centered.

        Args:
            width (int): New width in pixels.
            height (int): New height in pixels.
        """
        self.offset = Vector2(width / 2, height / 2)

    def world_to_screen(self, world_pos: Vector2) -> Vector2:
        """
        Transform a point from World Space to Screen Space.

        Formula: (WorldPos - CamPos) * Zoom + ScreenOffset

        Args:
            world_pos (Vector2): The coordinate in the game world.

        Returns:
            Vector2: The pixel coordinate on the screen.
        """
        # 1. Translate world to camera local
        local_pos = world_pos - self.position

        # 2. Scale (Zoom)
        local_pos = local_pos * self.zoom

        # 3. Rotate (around camera center)
        if self.rotation != 0:
            local_pos = local_pos.rotate(-self.rotation)

        screen_pos = local_pos + self.offset

        # 4. Translate to screen center
        return cast(Vector2, screen_pos)

    def screen_to_world(self, screen_pos: Vector2) -> Vector2:
        """
        Transform a point from Screen Space (e.g., Mouse) to World Space.

        This is the inverse of world_to_screen.
        Formula: (ScreenPos - ScreenOffset) / Zoom + CamPos

        Args:
            screen_pos (Vector2): The pixel coordinate (e.g., pygame.mouse.get_pos()).

        Returns:
            Vector2: The coordinate in the game world.
        """
        # 1. Translate screen to center relative
        local_pos = screen_pos - self.offset

        # 2. Inverse Rotate
        if self.rotation != 0:
            local_pos = local_pos.rotate(self.rotation)

        # 3. Inverse Scale
        # Avoid division by zero
        safe_zoom = self.zoom if self.zoom != 0 else 0.001
        local_pos = local_pos * (1.0 / safe_zoom)
        world_pos = local_pos + self.position

        # 4. Translate back to world
        return cast(Vector2, world_pos)

    def get_view_bounds(self) -> Rect:
        """
        Calculate the visible rectangle of the world in World Coordinates.

        Useful for Culling (not rendering objects outside this rect) or
        keeping the player inside bounds.

        Note:
            This approximation assumes no rotation for the bounding box calculation.
            If rotation is used, this returns a generic AABB that fits the view.

        Returns:
            Rect: The rectangle representing the visible world area.
        """
        # Calculate the size of the view in world units
        # ScreenSize / Zoom
        view_width = (self.offset.x * 2) / self.zoom
        view_height = (self.offset.y * 2) / self.zoom

        # Top-left corner in world space
        left = self.position.x - (view_width / 2)
        top = self.position.y - (view_height / 2)

        return Rect(left, top, view_width, view_height)
