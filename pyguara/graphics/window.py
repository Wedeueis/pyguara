"""Core Window management module."""

from collections.abc import Iterable
from typing import Any

from pyguara.common.types import Color
from pyguara.config.types import WindowConfig
from pyguara.graphics.protocols import IWindowBackend
from pyguara.log import get_logger

logger = get_logger(__name__)


class Window:
    """The high-level manager for the application window.

    Encapsulates the lifecycle (create, destroy, present) of the OS window.
    """

    def __init__(self, config: WindowConfig, backend: IWindowBackend) -> None:
        """Initialize the Window wrapper."""
        self._config = config
        self._backend = backend
        self._native_handle: Any | None = None
        self._is_open: bool = False

    def create(self) -> None:
        """Initialize the actual OS window via the backend."""
        if self._is_open:
            return

        if self._backend.open(self._config):
            logger.info("Window opened successfully")
        else:
            raise RuntimeError("Failed to initialize window backend")

        self._native_handle = self._backend.get_screen()

        self._is_open = True

    def close(self) -> None:
        """Destroy the window."""
        if self._is_open:
            self._backend.close()
            self._native_handle = None
            self._is_open = False

    def clear(self, color: Color | None = None) -> None:
        """Fill the window with a colour.

        Args:
            color: Colour to fill with. When None, the backend uses the
                `default_color` it took from `WindowConfig` at open time.
        """
        self._backend.clear(color)

    def present(self) -> None:
        """Update the window with the latest rendered frame."""
        self._backend.present()

    def poll_events(self) -> Iterable[Any]:
        """Pump the OS event queue and return this frame's engine events.

        Returns:
            Engine events (`pyguara.events.input` / `.lifecycle` / `.window`) --
            `QuitEvent`, `KeyDownEvent`, `KeyUpEvent`, `MouseButtonEvent`,
            `MouseMotionEvent`, `WindowResizeEvent`. The backend translates its
            native events into these (issue #9), so no caller touches SDL.
        """
        return self._backend.poll_events()

    def set_title(self, title: str) -> None:
        """Update the window title dynamically."""
        self._config.title = title
        self._backend.set_caption(title)

    @property
    def native_handle(self) -> Any:
        """Retrieve the raw underlying window object/surface."""
        if self._native_handle is None:
            raise RuntimeError("Window not created. Call create() first.")
        return self._native_handle

    @property
    def width(self) -> int:
        """The drawable width in pixels.

        Reported by the backend once the window exists, since the OS need not
        grant the size that was asked for -- a fullscreen window is commonly
        given the desktop resolution instead. Falls back to the configured
        width before `create()`.

        Returning the configured value unconditionally is what fed a wrong
        screen size to `SceneManager.set_screen_size()`, and from there to
        transitions and viewport calculations, whenever the two differed.
        """
        if self._is_open:
            return self._backend.width
        return self._config.screen_width

    @property
    def height(self) -> int:
        """The drawable height in pixels.

        Backend-reported once the window exists; see `width`.
        """
        if self._is_open:
            return self._backend.height
        return self._config.screen_height

    @property
    def is_open(self) -> bool:
        """Check if the window has been created and is active."""
        return self._is_open
