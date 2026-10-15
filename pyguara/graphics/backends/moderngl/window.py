"""Pygame-based OpenGL window implementation for ModernGL backend."""

from collections.abc import Iterable
from typing import Any

import pygame

import moderngl
from pyguara.common.types import Color
from pyguara.config.types import WindowConfig
from pyguara.graphics.backends.pygame.events import translate_events
from pyguara.log import get_logger

logger = get_logger(__name__)


def display_flags(config: WindowConfig) -> int:
    """Return the SDL display flags `config` asks for.

    Its own function so the mapping can be asserted without opening a
    window: every one of these is decided once, at creation, and SDL will
    not change most of them afterwards -- which is exactly why getting one
    wrong is expensive to find.

    Args:
        config: The window configuration.

    Returns:
        The flag mask for `pygame.display.set_mode`.
    """
    flags = pygame.OPENGL | pygame.DOUBLEBUF
    if config.fullscreen:
        flags |= pygame.FULLSCREEN
    if getattr(config, "borderless", False):
        # The OS title bar is removed and the editor draws its own. Only
        # useful with `resizable`, since a borderless window the user
        # cannot drag an edge of is a window they cannot size.
        flags |= pygame.NOFRAME
    if getattr(config, "resizable", False):
        # Without this SDL emits no resize event at all. A window manager
        # may still let the frame be maximised -- WSLg does -- and the GL
        # drawable then grows while nothing in the engine is told, so
        # everything carries on rendering at the starting resolution into
        # a corner of a much larger window.
        flags |= pygame.RESIZABLE
    return flags


class PygameGLWindow:
    """Window backend using Pygame with OpenGL context for ModernGL rendering.

    This implementation creates a Pygame window with OpenGL 3.3+ Core Profile
    attributes, enabling ModernGL to create a context for GPU-accelerated rendering.

    The window handles:
    - OpenGL context creation and management
    - Event polling (input, window events)
    - Buffer swapping (double buffering)
    """

    def __init__(self) -> None:
        """Initialize the OpenGL window backend."""
        self._screen: Any = None
        self._ctx: moderngl.Context | None = None
        self._default_color = Color(0, 0, 0)
        self._is_open = False
        self._width = 0
        self._height = 0
        self._window_object: Any = None
        self._is_maximized = False

    def open(self, config: WindowConfig) -> bool:
        """Create a Pygame display with OpenGL context.

        Sets up OpenGL 3.3+ Core Profile before creating the window,
        then initializes the ModernGL context.

        Args:
            config: Window configuration settings.

        Returns:
            True if window was created successfully.
        """
        self._default_color = config.default_color
        self._width = config.screen_width
        self._height = config.screen_height

        # `set_mode()` initialises the display module implicitly, which is
        # why the pygame backend gets away without this -- but
        # `gl_set_attribute()` does not, and raises "video system not
        # initialized" when it is the first display call in the process.
        # It is idempotent, so calling it here costs nothing when the
        # caller has already initialised pygame.
        pygame.display.init()

        # Set OpenGL attributes before creating display
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(
            pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE
        )

        # Enable multisampling for smoother edges (optional)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)

        flags = display_flags(config)

        # Create the window.
        #
        # `vsync=1` is a hard request, not a hint: SDL raises "regular
        # vsync for OpenGL not available" outright where the driver cannot
        # provide it, and the whole game fails to start. That is the case
        # on WSLg (Mesa/D3D12), among others. A missing frame-rate cap is
        # not worth refusing to open a window over, so fall back and say
        # so rather than dying.
        size = (config.screen_width, config.screen_height)
        try:
            self._screen = pygame.display.set_mode(
                size, flags, vsync=1 if config.vsync else 0
            )
        except pygame.error:
            if not config.vsync:
                raise
            logger.warning(
                "OpenGL vsync unavailable on this driver; opening without it."
            )
            self._screen = pygame.display.set_mode(size, flags, vsync=0)
        pygame.display.set_caption(config.title)

        # Create ModernGL context from the current OpenGL context
        self._ctx = moderngl.create_context()

        # Blending is deliberately not set up here: it is renderer state,
        # and `ModernGLRenderer` applies it (see `blend.py`). A window that
        # configured it would only hide a renderer that did not.

        self._is_open = True
        return True

    def close(self) -> None:
        """Close the window and release OpenGL resources."""
        if self._ctx is not None:
            self._ctx.release()
            self._ctx = None

        pygame.display.quit()
        self._is_open = False

    def set_caption(self, title: str) -> None:
        """Set the window title."""
        pygame.display.set_caption(title)

    def present(self) -> None:
        """Swap display buffers to show the rendered frame."""
        pygame.display.flip()

    def clear(self, color: Color | None = None) -> None:
        """Clear the screen using OpenGL.

        Args:
            color: Optional color to clear with. Uses default if not provided.
        """
        if not self._is_open or self._ctx is None:
            return

        fill_color = color if color is not None else self._default_color
        # Normalize color from 0-255 to 0.0-1.0 for OpenGL
        r = fill_color[0] / 255.0
        g = fill_color[1] / 255.0
        b = fill_color[2] / 255.0
        a = fill_color[3] / 255.0 if len(fill_color) > 3 else 1.0

        self._ctx.clear(r, g, b, a)

    def minimize(self) -> None:
        """Iconify the window."""
        window = self._native_window()
        if window is not None:
            window.minimize()

    def maximize(self) -> None:
        """Fill the work area."""
        window = self._native_window()
        if window is not None:
            window.maximize()
            self._is_maximized = True

    def restore(self) -> None:
        """Return to the size before maximising."""
        window = self._native_window()
        if window is not None:
            window.restore()
            self._is_maximized = False

    @property
    def is_maximized(self) -> bool:
        """Whether the window currently fills the work area.

        SDL exposes no direct query through pygame, so this tracks what
        was asked for. A user maximising through the window manager's own
        control is not seen -- which is a cosmetic wrong arrow on the
        restore button, not a wrong window.
        """
        return self._is_maximized

    def move_by(self, dx: int, dy: int) -> None:
        """Move the window by a screen-space delta.

        Args:
            dx: Horizontal movement in pixels.
            dy: Vertical movement in pixels.
        """
        window = self._native_window()
        if window is None:
            return
        try:
            x, y = window.position
            window.position = (int(x + dx), int(y + dy))
        except Exception as exc:  # pragma: no cover - depends on the WM
            logger.debug(f"Could not move the window: {exc}")

    def request_close(self) -> None:
        """Ask the application to shut down, as the OS close button does.

        Posts a quit onto the event queue rather than destroying the
        window: a borderless window's close button is pressed from inside
        a frame that is still being drawn, and tearing the GL context down
        underneath it would take the frame with it. Through the queue, the
        next `poll_events` reports it and the application runs the same
        shutdown it runs for the OS's own button.
        """
        try:
            pygame.event.post(pygame.event.Event(pygame.QUIT))
        except Exception as exc:  # pragma: no cover - a full event queue
            logger.debug(f"Could not post a quit event: {exc}")

    def _native_window(self) -> Any:
        """Return pygame's window object, or None where it is unavailable.

        Built lazily and cached: `from_display_module()` warns about
        surface rendering, which is irrelevant here -- the window is a GL
        drawable -- and there is no reason to hear it twice.
        """
        if self._window_object is not None:
            return self._window_object
        try:
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                self._window_object = pygame.Window.from_display_module()
        except Exception as exc:  # pragma: no cover - old pygame, odd driver
            logger.debug(f"No window object available: {exc}")
            return None
        return self._window_object

    def poll_events(self) -> Iterable[Any]:
        """Pump SDL and return engine events (see `pygame.events`)."""
        if not self._is_open:
            return []

        raw_events = pygame.event.get()

        for event in raw_events:
            if event.type == pygame.QUIT:
                self._is_open = False

        return translate_events(raw_events)

    def get_screen(self) -> moderngl.Context:
        """Return the ModernGL context.

        Unlike the Pygame backend which returns a Surface,
        this returns the ModernGL context for GPU rendering.

        Returns:
            The ModernGL context instance.

        Raises:
            RuntimeError: If context is not initialized.
        """
        if self._ctx is None:
            raise RuntimeError("OpenGL context not initialized. Call open() first.")
        return self._ctx

    @property
    def context(self) -> moderngl.Context | None:
        """Get the ModernGL context directly."""
        return self._ctx

    @property
    def width(self) -> int:
        """Get the window width in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Get the window height in pixels."""
        return self._height
