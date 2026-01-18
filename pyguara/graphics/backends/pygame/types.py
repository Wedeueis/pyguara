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


class PygameTextureFactory:
    """Factory for creating PygameTexture instances from raw image data."""

    def create_from_bytes(
        self, path: str, data: bytes, width: int, height: int
    ) -> Texture:
        """Create a PygameTexture from raw RGBA pixel data.

        Args:
            path: Identifier/name for the texture.
            data: Raw RGBA pixel data (4 bytes per pixel).
            width: Width of the image in pixels.
            height: Height of the image in pixels.

        Returns:
            A PygameTexture wrapping a pygame.Surface.
        """
        # Create surface from raw bytes with alpha channel
        surface = pygame.Surface((width, height), pygame.SRCALPHA)
        # Copy raw bytes into the surface
        # pygame.image.frombytes expects the display to be initialized for some formats
        # So we manually set pixels from the raw data
        raw_surface = pygame.image.frombytes(data, (width, height), "RGBA")
        surface.blit(raw_surface, (0, 0))

        # Convert for optimal blitting if display is initialized
        if pygame.display.get_surface() is not None:
            surface = surface.convert_alpha()

        return PygameTexture(path, surface)
