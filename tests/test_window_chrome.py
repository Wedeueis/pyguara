"""The window flags and the controls the editor's title bar drives.

Both halves of "modern chrome" meet here: `display.resizable` and
`display.borderless` decide what SDL creates, and `Window.chrome` decides
whether the editor may draw a bar at all. Neither opens a window --
`display_flags` is a pure mapping, and `chrome` is a protocol check.
"""

from __future__ import annotations

import pygame
import pytest

from pyguara.config.types import WindowConfig
from pyguara.graphics.backends.pygame.pygame_window import PygameWindow
from pyguara.graphics.backends.wgpu.window import WgpuWindow
from pyguara.graphics.protocols import IWindowChrome
from pyguara.graphics.window import Window


class _NoChrome:
    """A backend with no window controls, as a headless one has none."""

    def open(self, config: WindowConfig) -> bool:  # pragma: no cover - unused
        return True


class _WithChrome(_NoChrome):
    """A backend that can drive its own window."""

    def minimize(self) -> None: ...
    def maximize(self) -> None: ...
    def restore(self) -> None: ...
    def request_close(self) -> None: ...
    def begin_move(self) -> None: ...
    def move_by(self, dx: int, dy: int) -> None: ...
    def end_move(self) -> None: ...

    @property
    def is_maximized(self) -> bool:
        return False


def display_flags(config: object) -> int:
    """The flags the wgpu window -- the one Studio's chrome needs -- opens with."""
    return WgpuWindow().display_flags(config)  # type: ignore[arg-type]


@pytest.mark.unit
class TestConfig:
    def test_both_flags_default_off(self) -> None:
        config = WindowConfig()
        assert config.resizable is False
        assert config.borderless is False

    def test_a_plain_window_is_neither(self) -> None:
        flags = display_flags(WindowConfig())
        assert not flags & pygame.RESIZABLE
        assert not flags & pygame.NOFRAME

    def test_resizable_sets_the_sdl_flag(self) -> None:
        flags = display_flags(WindowConfig(resizable=True))
        assert flags & pygame.RESIZABLE
        assert not flags & pygame.NOFRAME

    def test_borderless_removes_the_frame(self) -> None:
        flags = display_flags(WindowConfig(borderless=True))
        assert flags & pygame.NOFRAME

    def test_the_two_combine(self) -> None:
        flags = display_flags(WindowConfig(resizable=True, borderless=True))
        assert flags & pygame.RESIZABLE
        assert flags & pygame.NOFRAME

    def test_no_opengl_surface_is_asked_for(self) -> None:
        """wgpu draws to the native handle; SDL's own GL surface would
        compete for it (and the pygame window strips it for that reason)."""
        flags = display_flags(WindowConfig(resizable=True, borderless=True))
        assert not flags & pygame.OPENGL

    def test_the_software_window_ignores_both(self) -> None:
        """No editor draws its own title bar over a software window."""
        flags = PygameWindow().display_flags(
            WindowConfig(resizable=True, borderless=True)
        )
        assert not flags & (pygame.RESIZABLE | pygame.NOFRAME)

    def test_fullscreen_still_works_alongside_them(self) -> None:
        flags = display_flags(WindowConfig(fullscreen=True, resizable=True))
        assert flags & pygame.FULLSCREEN
        assert flags & pygame.RESIZABLE

    def test_a_config_predating_the_fields_is_tolerated(self) -> None:
        class Older:
            fullscreen = False

        assert display_flags(Older()) == 0


@pytest.mark.unit
class TestChromeExposure:
    def test_a_backend_with_controls_is_exposed(self) -> None:
        backend = _WithChrome()
        window = Window(WindowConfig(), backend)  # type: ignore[arg-type]
        assert window.chrome is backend

    def test_a_backend_without_them_exposes_nothing(self) -> None:
        window = Window(WindowConfig(), _NoChrome())  # type: ignore[arg-type]
        assert window.chrome is None

    def test_the_protocol_matches_the_same_way(self) -> None:
        assert isinstance(_WithChrome(), IWindowChrome)
        assert not isinstance(_NoChrome(), IWindowChrome)


@pytest.mark.unit
def test_the_wgpu_window_offers_the_controls() -> None:
    """Studio's title bar drives these; they lived on the ModernGL window."""
    assert isinstance(WgpuWindow(), IWindowChrome)
