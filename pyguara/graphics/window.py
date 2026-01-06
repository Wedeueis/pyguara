"""Core Window management module."""

from typing import Any, Optional, Iterable
from pyguara.config.types import WindowConfig
from pyguara.graphics.protocols import IWindowBackend
from pyguara.common.types import Color


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
            print("Sucessefully openned window!")
        else:
            raise Exception("Cannot load pygame window!")

        self._native_handle = self._backend.get_screen()

        self._is_open = True

    def close(self) -> None:
        """Destroy the window."""
        if self._is_open:
            self._backend.close()
            self._native_handle = None
            self._is_open = False

    def clear(self, color: Optional[Color] = None) -> None:
        """Clear the window with configured default Color."""
        self._backend.clear(color)

    def present(self) -> None:
        """Update the window with the latest rendered frame."""
        self._backend.present()

    def poll_events(self) -> Iterable[Any]:
        """Fetch pygame events and handle internal window state."""
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
        """Get the configured window width."""
        return self._config.screen_width

    @property
    def height(self) -> int:
        """Get the configured window height."""
        return self._config.screen_height

    @property
    def is_open(self) -> bool:
        """Check if the window has been created and is active."""
        return self._is_open
