"""Concrete loaders for Pygame assets."""

from typing import List
import pygame
from pyguara.resources.loader import IResourceLoader
from pyguara.resources.types import Resource
from .types import PygameTexture


class PygameImageLoader(IResourceLoader):
    """Load the image file into PygameTexture objects."""

    @property
    def supported_extensions(self) -> List[str]:
        """Returns a list of supported extensions."""
        return [".png", ".jpg", ".jpeg", ".bmp", ".tga"]

    def load(self, path: str) -> Resource:
        """
        Load a Texture from a file using.

        Note:
            Requires pygame.display.set_mode() to be called beforehand
            if internal format conversion is performed.
        """
        surface = pygame.image.load(path).convert_alpha()
        return PygameTexture(path, surface)
