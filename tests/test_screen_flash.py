"""Tests for `ScreenFlash` (pyguara/graphics/components/screen_flash.py)."""

from __future__ import annotations

from pyguara.common.types import Color, Rect
from pyguara.graphics.components.screen_flash import ScreenFlash

_VIEWPORT = Rect(0, 0, 800, 600)


class _FakeRenderer:
    def __init__(self) -> None:
        self.draw_rect_calls: list[tuple[Rect, Color]] = []

    def draw_rect(self, rect: Rect, color: Color, width: int = 0) -> None:
        self.draw_rect_calls.append((rect, color))


def test_idle_flash_is_not_active() -> None:
    flash = ScreenFlash()

    assert flash.is_active is False


def test_trigger_activates_it() -> None:
    flash = ScreenFlash()

    flash.trigger(Color(255, 0, 0), duration=0.2)

    assert flash.is_active is True


def test_render_is_a_noop_while_idle() -> None:
    flash = ScreenFlash()
    renderer = _FakeRenderer()

    flash.render(renderer, _VIEWPORT)

    assert renderer.draw_rect_calls == []


def test_render_draws_the_full_viewport_at_full_alpha_right_after_trigger() -> None:
    flash = ScreenFlash()
    flash.trigger(Color(255, 0, 0, 200), duration=0.2)
    renderer = _FakeRenderer()

    flash.render(renderer, _VIEWPORT)

    rect, color = renderer.draw_rect_calls[0]
    assert rect == _VIEWPORT
    assert (color.r, color.g, color.b, color.a) == (255, 0, 0, 200)


def test_update_fades_alpha_toward_zero() -> None:
    flash = ScreenFlash()
    flash.trigger(Color(255, 0, 0, 200), duration=1.0)
    renderer = _FakeRenderer()

    flash.update(0.5)  # half the duration elapsed
    flash.render(renderer, _VIEWPORT)

    _, color = renderer.draw_rect_calls[0]
    assert 90 < color.a < 110  # ~100, roughly half of 200


def test_update_clears_the_flash_once_duration_elapses() -> None:
    flash = ScreenFlash()
    flash.trigger(Color(255, 0, 0), duration=0.2)

    flash.update(0.3)

    assert flash.is_active is False


def test_render_after_expiry_is_a_noop() -> None:
    flash = ScreenFlash()
    flash.trigger(Color(255, 0, 0), duration=0.1)
    flash.update(0.2)
    renderer = _FakeRenderer()

    flash.render(renderer, _VIEWPORT)

    assert renderer.draw_rect_calls == []


def test_retriggering_replaces_rather_than_stacks() -> None:
    flash = ScreenFlash()
    flash.trigger(Color(255, 0, 0, 200), duration=1.0)
    flash.update(0.9)  # nearly faded

    flash.trigger(Color(0, 255, 0, 100), duration=1.0)  # retrigger resets it
    renderer = _FakeRenderer()
    flash.render(renderer, _VIEWPORT)

    _, color = renderer.draw_rect_calls[0]
    assert (color.r, color.g, color.b, color.a) == (0, 255, 0, 100)


def test_zero_duration_does_not_raise() -> None:
    flash = ScreenFlash()
    flash.trigger(Color(255, 0, 0), duration=0.0)
    renderer = _FakeRenderer()

    flash.render(renderer, _VIEWPORT)  # must not raise ZeroDivisionError

    _, color = renderer.draw_rect_calls[0]
    assert color.a == 0
