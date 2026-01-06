"""Pygame implementation of the Window Backend."""

import pygame
from typing import Any, Iterable, Optional, cast
from pyguara.config.types import WindowConfig
from pyguara.graphics.protocols import IWindowBackend
from pyguara.common.types import Color


class PygameWindow(IWindowBackend):
    """Handles window lifecycle using Pygame."""

    def __init__(self) -> None:
        """Initialize Pygame Window."""
        self._screen: Any = None
        self._default_color = Color(0, 0, 0)
        self._is_open = False

    def open(self, config: WindowConfig) -> bool:
        """Create a Pygame display surface."""
        # Standard Pygame setup
        # flags = pygame.DOUBLEBUF | pygame.HWSURFACE
        # For Linux WSL
        flags = 0
        self._default_color = config.default_color
        if config.fullscreen:
            flags |= pygame.FULLSCREEN

        self._screen = pygame.display.set_mode(
            (config.screen_width, config.screen_height),
            flags,
            vsync=1 if config.vsync else 0,
        )
        pygame.display.set_caption(config.title)
        self._is_open = True
        return True

    def close(self) -> None:
        """Quit the display module."""
        # Pygame uses quit() to kill the window context
        pygame.display.quit()
        self._is_open = False

    def set_caption(self, title: str) -> None:
        """Set the window title."""
        pygame.display.set_caption(title)

    def present(self) -> None:
        """Flip the display buffer."""
        # The window manages the flip, not the renderer
        pygame.display.flip()

    def clear(self, color: Optional[Color] = None) -> None:
        """Clear the window context screen with default clear color."""
        if self._is_open and self._screen:
            fill_color = color if color is not None else self._default_color
            self._screen.fill(fill_color)

    def poll_events(self) -> Iterable[Any]:
        """Fetch pygame events and handle internal window state."""
        if not self._is_open:
            return []

        events = pygame.event.get()

        # Check for quit event internally to update state
        for event in events:
            if event.type == pygame.QUIT:
                self._is_open = False

        return cast(Iterable[Any], events)

    def get_screen(self) -> Any:
        """Return the native OS window."""
        return self._screen
