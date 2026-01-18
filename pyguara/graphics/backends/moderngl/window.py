"""Pygame-based OpenGL window implementation for ModernGL backend."""

import pygame
import moderngl
from typing import Any, Iterable, Optional, cast

from pyguara.config.types import WindowConfig
from pyguara.graphics.protocols import IWindowBackend
from pyguara.common.types import Color


class PygameGLWindow(IWindowBackend):
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
        self._ctx: Optional[moderngl.Context] = None
        self._default_color = Color(0, 0, 0)
        self._is_open = False
        self._width = 0
        self._height = 0

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

        # Set OpenGL attributes before creating display
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 3)
        pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 3)
        pygame.display.gl_set_attribute(
            pygame.GL_CONTEXT_PROFILE_MASK, pygame.GL_CONTEXT_PROFILE_CORE
        )

        # Enable multisampling for smoother edges (optional)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLEBUFFERS, 1)
        pygame.display.gl_set_attribute(pygame.GL_MULTISAMPLESAMPLES, 4)

        # Build display flags
        flags = pygame.OPENGL | pygame.DOUBLEBUF
        if config.fullscreen:
            flags |= pygame.FULLSCREEN

        # Create the window
        self._screen = pygame.display.set_mode(
            (config.screen_width, config.screen_height),
            flags,
            vsync=1 if config.vsync else 0,
        )
        pygame.display.set_caption(config.title)

        # Create ModernGL context from the current OpenGL context
        self._ctx = moderngl.create_context()

        # Enable blending for alpha transparency
        self._ctx.enable(moderngl.BLEND)
        self._ctx.blend_func = (
            moderngl.SRC_ALPHA,
            moderngl.ONE_MINUS_SRC_ALPHA,
        )

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

    def clear(self, color: Optional[Color] = None) -> None:
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

    def poll_events(self) -> Iterable[Any]:
        """Fetch pygame events and handle internal window state.

        Returns:
            Iterable of pygame event objects.
        """
        if not self._is_open:
            return []

        events = pygame.event.get()

        for event in events:
            if event.type == pygame.QUIT:
                self._is_open = False

        return cast(Iterable[Any], events)

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
    def context(self) -> Optional[moderngl.Context]:
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
