"""Pygame implementation of the Window Backend."""

from collections.abc import Iterable
from typing import Any

import pygame

from pyguara.common.types import Color
from pyguara.config.types import WindowConfig
from pyguara.graphics.backends.pygame.conversions import to_pygame_color
from pyguara.graphics.backends.pygame.events import translate_events
from pyguara.log import get_logger

logger = get_logger(__name__)


class PygameWindow:
    """Handles window lifecycle using Pygame."""

    def __init__(self) -> None:
        """Initialize Pygame Window."""
        self._screen: Any = None
        self._default_color = Color(0, 0, 0)
        self._is_open = False

    def open(self, config: WindowConfig) -> bool:
        """Create the display surface.

        Args:
            config: Window settings to open with.

        Returns:
            True once the surface exists.
        """
        flags = 0
        self._default_color = config.default_color
        if config.fullscreen:
            flags |= pygame.FULLSCREEN

        size = (config.screen_width, config.screen_height)
        screen: pygame.Surface = pygame.display.set_mode(
            size, flags, vsync=1 if config.vsync else 0
        )

        if config.vsync and not (flags & pygame.OPENGL):
            screen = self._drop_vsync_if_promoted_to_opengl(screen, size, flags)
        self._screen = screen

        pygame.display.set_caption(config.title)
        self._is_open = True
        return True

    def _drop_vsync_if_promoted_to_opengl(
        self, screen: pygame.Surface, size: tuple[int, int], flags: int
    ) -> pygame.Surface:
        """Drop vsync if honouring it turned the display into an OpenGL surface.

        SDL can only vsync a hardware-presented surface, so on drivers without
        a software vsync path pygame quietly adds `pygame.OPENGL` to satisfy
        the request. This renderer draws by blitting to the display surface,
        and blits to an OpenGL display surface are never presented -- the
        window opens, appears in the taskbar, and stays blank forever, with no
        error anywhere.

        A visible window without vsync beats an invisible one with it, so the
        surface is recreated without the request and the trade is logged.

        Args:
            screen: The surface `set_mode` just returned.
            size: Window size in pixels.
            flags: The flags originally requested.

        Returns:
            The display surface to use.
        """
        if not screen.get_flags() & pygame.OPENGL:
            return screen

        logger.warning(
            "This driver cannot vsync a software surface, so pygame promoted "
            "the window to OpenGL -- which this renderer cannot draw to, "
            "leaving the window blank. Recreating it without vsync. Set "
            "display.vsync = false to silence this."
        )
        replacement: pygame.Surface = pygame.display.set_mode(size, flags, vsync=0)
        return replacement

    @property
    def width(self) -> int:
        """The drawable surface width in pixels, read back from SDL."""
        if self._screen is None:
            return 0
        return int(self._screen.get_width())

    @property
    def height(self) -> int:
        """The drawable surface height in pixels, read back from SDL."""
        if self._screen is None:
            return 0
        return int(self._screen.get_height())

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

    def clear(self, color: Color | None = None) -> None:
        """Clear the window context screen with default clear color."""
        if self._is_open and self._screen:
            fill_color = color if color is not None else self._default_color
            self._screen.fill(to_pygame_color(fill_color))

    def poll_events(self) -> Iterable[Any]:
        """Pump SDL and return engine events (see `pygame.events`)."""
        if not self._is_open:
            return []

        raw_events = pygame.event.get()

        # Check for quit event internally to update state
        for event in raw_events:
            if event.type == pygame.QUIT:
                self._is_open = False

        return translate_events(raw_events)

    def get_screen(self) -> Any:
        """Return the native OS window."""
        return self._screen
