"""Tests for `FloatingText` (pyguara/graphics/components/floating_text.py)."""

from __future__ import annotations

from pyguara.common.types import Color, Vector2
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.floating_text import FloatingText


class _FakeRenderer:
    """Captures draw_text() calls; nothing else is needed for these tests."""

    def __init__(self) -> None:
        self.draw_text_calls: list[tuple[str, Vector2, Color, int]] = []

    def draw_text(
        self, text: str, position: Vector2, color: Color, size: int = 16
    ) -> None:
        self.draw_text_calls.append((text, position, color, size))


def test_spawn_activates_one_entry() -> None:
    ft = FloatingText(capacity=10)

    ft.spawn("+5", Vector2(0, 0))

    active = [e for e in ft._pool if e.active]
    assert len(active) == 1
    assert active[0].text == "+5"


def test_spawn_beyond_capacity_is_dropped() -> None:
    ft = FloatingText(capacity=2)

    ft.spawn("a", Vector2(0, 0), life=10.0)
    ft.spawn("b", Vector2(0, 0), life=10.0)
    ft.spawn("c", Vector2(0, 0), life=10.0)  # pool full, dropped

    active = [e for e in ft._pool if e.active]
    assert len(active) == 2


def test_update_moves_by_velocity() -> None:
    ft = FloatingText(capacity=4)
    ft.spawn("hi", Vector2(0, 0), velocity=Vector2(0, -40), life=1.0)

    ft.update(0.5)

    active = [e for e in ft._pool if e.active][0]
    assert active.position == Vector2(0, -20)


def test_update_expires_and_recycles_at_end_of_life() -> None:
    ft = FloatingText(capacity=4)
    ft.spawn("hi", Vector2(0, 0), life=1.0)

    ft.update(0.5)
    assert any(e.active for e in ft._pool)

    ft.update(0.6)  # total 1.1s
    assert not any(e.active for e in ft._pool)


def test_recycled_entry_is_available_for_a_new_spawn() -> None:
    ft = FloatingText(capacity=1)
    ft.spawn("a", Vector2(0, 0), life=0.1)
    ft.update(0.2)

    ft.spawn("b", Vector2(1, 1), life=1.0)

    active = [e for e in ft._pool if e.active]
    assert len(active) == 1
    assert active[0].text == "b"


def test_render_draws_active_entries_through_the_camera() -> None:
    ft = FloatingText(capacity=4)
    ft.spawn("+10", Vector2(100, 100), color=Color(255, 0, 0), size=20)
    camera = Camera2D(800, 600)
    renderer = _FakeRenderer()

    ft.render(renderer, camera)

    assert len(renderer.draw_text_calls) == 1
    text, position, color, size = renderer.draw_text_calls[0]
    assert text == "+10"
    assert size == 20
    assert position == camera.world_to_screen(Vector2(100, 100))


def test_render_skips_inactive_entries() -> None:
    ft = FloatingText(capacity=4)
    camera = Camera2D(800, 600)
    renderer = _FakeRenderer()

    ft.render(renderer, camera)

    assert renderer.draw_text_calls == []


def test_render_fades_alpha_toward_zero_as_life_runs_out() -> None:
    ft = FloatingText(capacity=4)
    ft.spawn("fade", Vector2(0, 0), color=Color(255, 255, 255, 255), life=1.0)
    camera = Camera2D(800, 600)
    renderer = _FakeRenderer()

    ft.update(0.5)  # half life remaining
    ft.render(renderer, camera)

    _, _, color, _ = renderer.draw_text_calls[0]
    assert 100 < color.a < 150  # ~127, roughly half of 255
