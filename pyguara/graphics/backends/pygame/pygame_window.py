"""Pygame implementation of the Window Backend."""

import pygame
from typing import Any
from pyguara.graphics.protocols import IWindowBackend


class PygameWindow(IWindowBackend):
    """Handles window lifecycle using Pygame."""

    def create_window(
        self, width: int, height: int, title: str, fullscreen: bool, vsync: bool
    ) -> Any:
        """Create a Pygame display surface."""
        # Standard Pygame setup
        flags = pygame.DOUBLEBUF | pygame.HWSURFACE
        if fullscreen:
            flags |= pygame.FULLSCREEN

        surface = pygame.display.set_mode(
            (width, height), flags, vsync=1 if vsync else 0
        )
        pygame.display.set_caption(title)
        return surface

    def destroy_window(self) -> None:
        """Quit the display module."""
        # Pygame uses quit() to kill the window context
        pygame.display.quit()

    def set_caption(self, title: str) -> None:
        """Set the window title."""
        pygame.display.set_caption(title)

    def present(self) -> None:
        """Flip the display buffer."""
        # The window manages the flip, not the renderer
        pygame.display.flip()
