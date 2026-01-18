"""Resource loaders for ModernGL backend."""

from typing import List

import moderngl
import pygame

from pyguara.resources.loader import IResourceLoader
from pyguara.resources.types import Resource
from pyguara.graphics.backends.moderngl.texture import GLTexture


class GLTextureLoader(IResourceLoader):
    """Load image files into GPU textures for ModernGL rendering.

    Uses pygame.image to load the file, then uploads the pixel data
    to the GPU via ModernGL. The resulting GLTexture can be used
    with the ModernGLRenderer for hardware-accelerated drawing.
    """

    def __init__(self, ctx: moderngl.Context) -> None:
        """Initialize the loader with a ModernGL context.

        Args:
            ctx: The ModernGL context to create textures in.
        """
        self._ctx = ctx

    @property
    def supported_extensions(self) -> List[str]:
        """Return supported image file extensions."""
        return [".png", ".jpg", ".jpeg", ".bmp", ".tga"]

    def load(self, path: str) -> Resource:
        """Load an image file and create a GPU texture.

        The image is loaded via pygame, flipped vertically (OpenGL uses
        bottom-left origin), converted to RGBA bytes, and uploaded to GPU.

        Args:
            path: Full path to the image file.

        Returns:
            A GLTexture resource ready for rendering.

        Raises:
            FileNotFoundError: If the file doesn't exist.
            pygame.error: If the image format is unsupported.
        """
        # Load the image using pygame
        surface = pygame.image.load(path)

        # Convert to RGBA format
        surface = surface.convert_alpha()

        # Get dimensions
        width = surface.get_width()
        height = surface.get_height()

        # Flip vertically for OpenGL (origin at bottom-left)
        surface = pygame.transform.flip(surface, False, True)

        # Get raw pixel data as bytes (RGBA format)
        # pygame surfaces are in RGBA format when using convert_alpha()
        data = pygame.image.tobytes(surface, "RGBA", False)

        # Create the GPU texture
        gl_texture = self._ctx.texture((width, height), 4, data)

        # Set texture parameters
        gl_texture.filter = (moderngl.LINEAR, moderngl.LINEAR)
        gl_texture.swizzle = "BGRA"  # pygame uses BGRA internally

        return GLTexture(path, gl_texture, width, height)
