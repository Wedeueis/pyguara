"""Pygame-specific implementations of Resource types (Adapter Pattern)."""

import pygame
from pyguara.resources.types import Texture


class PygameTexture(Texture):
    """A concrete implementation of Texture using pygame.Surface."""

    def __init__(self, path: str, surface: pygame.Surface):
        """
        Initialize the Pygame texture.

        Args:
            path (str): The source file path.
            surface (pygame.Surface): The loaded pygame image object.
        """
        super().__init__(path)
        self._surface = surface

    @property
    def width(self) -> int:
        """Get the width of the texture in pixels."""
        return int(self._surface.get_width())

    @property
    def height(self) -> int:
        """Get the height of the texture in pixels."""
        return int(self._surface.get_height())

    @property
    def native_handle(self) -> pygame.Surface:
        """Returns the internal pygame.Surface."""
        return self._surface
