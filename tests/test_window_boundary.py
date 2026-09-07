"""Tests for the Window/IWindowBackend boundary.

`Window` is the engine's only sanctioned view of the OS window, so what it
reports has to come from the backend rather than from the configuration that
merely *asked* for a window of that shape.
"""

from typing import Any

import pytest

from pyguara.common.types import Color
from pyguara.config.types import WindowConfig
from pyguara.graphics.backends.headless_renderer import HeadlessWindowBackend
from pyguara.graphics.protocols import IWindowBackend
from pyguara.graphics.window import Window


class GrantsADifferentSize:
    """A backend that is handed a size other than the one requested.

    This is ordinary behaviour, not a contrivance: a fullscreen window is
    commonly given the desktop resolution instead of what was asked for.
    """

    def __init__(self, granted_width: int, granted_height: int) -> None:
        self._width = granted_width
        self._height = granted_height
        self.cleared_with: list[Color | None] = []
        self.caption = ""

    def open(self, config: WindowConfig) -> bool:
        return True

    def close(self) -> None: ...

    def clear(self, color: Color | None = None) -> None:
        self.cleared_with.append(color)

    def set_caption(self, title: str) -> None:
        self.caption = title

    def present(self) -> None: ...

    def poll_events(self):
        return []

    def get_screen(self) -> Any:
        return object()

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height


@pytest.fixture
def config() -> WindowConfig:
    return WindowConfig(screen_width=800, screen_height=600, title="Test")


class TestReportedSize:
    def test_size_comes_from_the_backend_once_open(self, config) -> None:
        """Window.width returned the *configured* width unconditionally, so a
        window the OS sized differently reported the size that was asked for.
        Application feeds this to SceneManager.set_screen_size(), and from
        there it reaches transitions and viewport maths."""
        backend = GrantsADifferentSize(1920, 1080)
        window = Window(config, backend)
        window.create()

        assert window.width == 1920
        assert window.height == 1080

    def test_size_falls_back_to_config_before_create(self, config) -> None:
        window = Window(config, GrantsADifferentSize(1920, 1080))

        assert window.width == 800
        assert window.height == 600

    def test_size_falls_back_to_config_after_close(self, config) -> None:
        backend = GrantsADifferentSize(1920, 1080)
        window = Window(config, backend)
        window.create()
        window.close()

        assert window.width == 800


class TestBackendConformance:
    """Every shipped backend must satisfy IWindowBackend.

    The protocol declared no size accessors while ModernGL and headless
    implemented them and pygame did not -- a contract split three ways with
    nothing checking it.
    """

    def test_headless_window_backend_conforms(self) -> None:
        assert isinstance(HeadlessWindowBackend(), IWindowBackend)

    def test_pygame_window_backend_conforms(self) -> None:
        from pyguara.graphics.backends.pygame.pygame_window import PygameWindow

        assert isinstance(PygameWindow(), IWindowBackend)

    def test_headless_reports_the_size_it_was_opened_with(self) -> None:
        backend = HeadlessWindowBackend()
        backend.open(WindowConfig(screen_width=320, screen_height=240))

        assert (backend.width, backend.height) == (320, 240)

    def test_headless_reports_zero_before_open(self) -> None:
        backend = HeadlessWindowBackend()

        assert (backend.width, backend.height) == (0, 0)


class TestLifecycle:
    def test_create_is_idempotent(self, config) -> None:
        window = Window(config, GrantsADifferentSize(800, 600))
        window.create()
        window.create()

        assert window.is_open

    def test_native_handle_before_create_raises(self, config) -> None:
        window = Window(config, GrantsADifferentSize(800, 600))

        with pytest.raises(RuntimeError, match="Window not created"):
            _ = window.native_handle

    def test_a_backend_that_fails_to_open_raises_and_stays_closed(self, config) -> None:
        class RefusesToOpen(GrantsADifferentSize):
            def open(self, config: WindowConfig) -> bool:
                return False

        window = Window(config, RefusesToOpen(800, 600))

        with pytest.raises(RuntimeError, match="Failed to initialize"):
            window.create()
        assert not window.is_open

    def test_close_before_create_is_a_noop(self, config) -> None:
        window = Window(config, GrantsADifferentSize(800, 600))
        window.close()

        assert not window.is_open

    def test_set_title_updates_config_and_backend(self, config) -> None:
        backend = GrantsADifferentSize(800, 600)
        window = Window(config, backend)

        window.set_title("New Title")

        assert backend.caption == "New Title"
        assert config.title == "New Title"

    def test_clear_forwards_none_so_the_backend_uses_its_default(self, config) -> None:
        backend = GrantsADifferentSize(800, 600)
        window = Window(config, backend)

        window.clear()
        window.clear(Color(1, 2, 3))

        assert backend.cleared_with == [None, Color(1, 2, 3)]


class TestVsyncDoesNotBlankTheWindow:
    """SDL can only vsync a hardware-presented surface.

    On a driver with no software vsync path, pygame quietly satisfies
    `vsync=1` by adding `pygame.OPENGL` to the display. This renderer draws by
    blitting to the display surface, and blits to an OpenGL display surface are
    never presented -- so the window opens, appears in the taskbar and stays
    blank, with no error logged anywhere. Reproduced on WSLg/XWayland, where
    `set_mode((1280, 720), 0, vsync=1)` returns a surface with OPENGL set.
    """

    def test_the_display_is_never_left_as_an_opengl_surface(self) -> None:
        import pygame

        from pyguara.graphics.backends.pygame.pygame_window import PygameWindow

        pygame.init()
        window = PygameWindow()
        try:
            window.open(WindowConfig(screen_width=320, screen_height=240, vsync=True))
            surface = pygame.display.get_surface()

            assert surface is not None
            assert not surface.get_flags() & pygame.OPENGL, (
                "the renderer blits to the display surface, which an OpenGL "
                "surface never presents"
            )
        finally:
            pygame.display.quit()
            pygame.quit()

    def test_the_surface_is_still_usable_with_vsync_off(self) -> None:
        import pygame

        from pyguara.graphics.backends.pygame.pygame_window import PygameWindow

        pygame.init()
        window = PygameWindow()
        try:
            window.open(WindowConfig(screen_width=320, screen_height=240, vsync=False))
            surface = pygame.display.get_surface()

            assert surface is not None
            assert not surface.get_flags() & pygame.OPENGL
            assert (window.width, window.height) == (320, 240)
        finally:
            pygame.display.quit()
            pygame.quit()
