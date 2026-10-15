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
from pyguara.graphics.backends.moderngl.window import display_flags
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

    def test_gl_and_double_buffering_are_always_asked_for(self) -> None:
        flags = display_flags(WindowConfig(resizable=True, borderless=True))
        assert flags & pygame.OPENGL
        assert flags & pygame.DOUBLEBUF

    def test_fullscreen_still_works_alongside_them(self) -> None:
        flags = display_flags(WindowConfig(fullscreen=True, resizable=True))
        assert flags & pygame.FULLSCREEN
        assert flags & pygame.RESIZABLE

    def test_a_config_predating_the_fields_is_tolerated(self) -> None:
        class Older:
            fullscreen = False

        assert display_flags(Older()) == pygame.OPENGL | pygame.DOUBLEBUF


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
