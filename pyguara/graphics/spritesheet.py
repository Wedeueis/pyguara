"""
Utilities for handling sprite sheet assets.

This module provides the logic to slice a single large texture into multiple
smaller sub-textures (frames) that can be played back by the animation system.
"""

from typing import List
import pygame

from pyguara.resources.types import Texture
from pyguara.graphics.backends.pygame.types import PygameTexture


class SpriteSheet:
    """A wrapper around a Texture that knows how to slice itself."""

    def __init__(self, texture: Texture) -> None:
        """Initialize the sprite sheet with a source texture.

        Args:
            texture: The source image to slice up.
        """
        self._texture = texture
        self._frames: List[Texture] = []

    def slice_grid(
        self, frame_width: int, frame_height: int, count: int = 0
    ) -> List[Texture]:
        """
        Slices the texture into a grid of equal-sized frames.

        Args:
            frame_width (int): Width of a single frame.
            frame_height (int): Height of a single frame.
            count (int, optional): Total frames to grab. If 0, grabs as many as fit.

        Returns:
            List[Texture]: A list of new Texture objects, one for each frame.
        """
        sheet_width = self._texture.width
        sheet_height = self._texture.height

        # Calculate columns and rows
        cols = sheet_width // frame_width
        rows = sheet_height // frame_height

        total_possible = cols * rows
        frames_to_load = count if count > 0 else total_possible

        loaded = 0
        native_surf = self._texture.native_handle  # Assuming Pygame surface

        for y in range(rows):
            for x in range(cols):
                if loaded >= frames_to_load:
                    break

                # Define the rectangle area for this frame
                rect = pygame.Rect(
                    x * frame_width, y * frame_height, frame_width, frame_height
                )

                # Create a new surface for the frame
                # flags=pygame.SRCALPHA is crucial for transparency!
                frame_surf = pygame.Surface(rect.size, flags=pygame.SRCALPHA)

                # Blit only the specific area from the sheet onto the new frame
                frame_surf.blit(native_surf, (0, 0), rect)

                # Wrap it back into our Engine's Texture type
                # We name it logically: "sheet_name_0", "sheet_name_1", etc.
                frame_name = f"{self._texture.path}_{loaded}"
                new_tex = PygameTexture(frame_name, frame_surf)

                self._frames.append(new_tex)
                loaded += 1

        return self._frames
