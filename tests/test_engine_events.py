"""SDL -> engine event translation at the window boundary (issue #9).

The window backends pump SDL and hand the rest of the engine
`pyguara.events` objects, never raw pygame structs. These pin the mapping,
the key-code constants, and that `Application` now publishes
`WindowResizeEvent` (which previously had no publisher at all).
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
import pytest

from pyguara.events.input import (
    KeyDownEvent,
    KeyUpEvent,
    MouseButtonEvent,
    MouseMotionEvent,
)
from pyguara.events.lifecycle import QuitEvent
from pyguara.events.window import WindowResizeEvent
from pyguara.graphics.backends.pygame.events import translate_event, translate_events
from pyguara.input import keys


@pytest.fixture(autouse=True)
def _pygame_ready():
    pygame.init()
    yield
    pygame.quit()


class TestTranslateEvent:
    def test_quit_becomes_quit_event(self) -> None:
        assert isinstance(translate_event(pygame.event.Event(pygame.QUIT)), QuitEvent)

    def test_keydown_carries_the_key_code(self) -> None:
        raw = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE)
        out = translate_event(raw)
        assert isinstance(out, KeyDownEvent)
        assert out.key_code == pygame.K_SPACE == keys.SPACE

    def test_keyup_is_distinct_from_keydown(self) -> None:
        out = translate_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_a))
        assert isinstance(out, KeyUpEvent)
        assert not isinstance(out, KeyDownEvent)

    def test_mouse_button_down_carries_button_and_position(self) -> None:
        raw = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(120, 45))
        out = translate_event(raw)
        assert isinstance(out, MouseButtonEvent)
        assert (out.button, out.pos, out.is_down) == (1, (120, 45), True)

    def test_mouse_button_up_sets_is_down_false(self) -> None:
        raw = pygame.event.Event(pygame.MOUSEBUTTONUP, button=3, pos=(0, 0))
        out = translate_event(raw)
        assert isinstance(out, MouseButtonEvent)
        assert out.is_down is False

    def test_mouse_motion_carries_position_and_delta(self) -> None:
        raw = pygame.event.Event(pygame.MOUSEMOTION, pos=(10, 20), rel=(3, -4))
        out = translate_event(raw)
        assert isinstance(out, MouseMotionEvent)
        assert (out.pos, out.rel_x, out.rel_y) == ((10, 20), 3, -4)

    def test_videoresize_becomes_window_resize_event(self) -> None:
        raw = pygame.event.Event(pygame.VIDEORESIZE, w=800, h=600, size=(800, 600))
        out = translate_event(raw)
        assert isinstance(out, WindowResizeEvent)
        assert (out.width, out.height) == (800, 600)

    def test_an_unmapped_event_is_dropped(self) -> None:
        assert translate_event(pygame.event.Event(pygame.USEREVENT)) is None

    def test_translate_events_drops_the_unmapped_ones(self) -> None:
        raw = [
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a),
            pygame.event.Event(pygame.USEREVENT),
            pygame.event.Event(pygame.QUIT),
        ]
        out = translate_events(raw)
        assert [type(e) for e in out] == [KeyDownEvent, QuitEvent]


class TestKeyConstants:
    """`pyguara.input.keys` values must stay equal to pygame's, since key
    codes pass straight through the translator."""

    @pytest.mark.parametrize(
        "name",
        ["F1", "F5", "F9", "F12", "ESCAPE", "SPACE", "TAB", "Q", "W", "E", "S"],
    )
    def test_matches_pygame(self, name: str) -> None:
        pygame_name = "K_" + (name if len(name) > 1 else name.lower())
        assert getattr(keys, name) == getattr(pygame, pygame_name)

    def test_key_name_round_trips(self) -> None:
        assert keys.key_name(keys.F9) == "F9"
        assert keys.key_name(-1).startswith("KEY_")
