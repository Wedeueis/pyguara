"""Translucent colours blend in the world renderers, and text fades.

`pygame.draw` replaces the pixels it touches, alpha included, and the pygame
world renderer drew straight onto the opaque display: a `ScreenFlash` meant
as a faint red wash painted the whole screen solid red. And `Font.render`
ignores a colour's alpha on every backend, so `FloatingText` never faded.
"""

from __future__ import annotations

import os
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import numpy as np
import pygame
import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.graphics.backends.surface_blending import render_text
from pyguara.graphics.components.screen_flash import ScreenFlash

_SIZE = 64


@pytest.fixture(autouse=True, scope="module")
def _pygame() -> Any:
    pygame.init()
    yield


def _white() -> tuple[pygame.Surface, PygameBackend]:
    surface = pygame.Surface((_SIZE, _SIZE))
    surface.fill((255, 255, 255))
    return surface, PygameBackend(surface)


def _black() -> tuple[pygame.Surface, PygameBackend]:
    surface = pygame.Surface((_SIZE, _SIZE))
    surface.fill((0, 0, 0))
    return surface, PygameBackend(surface)


def _centre(surface: pygame.Surface) -> tuple[int, int, int]:
    r, g, b, _ = surface.get_at((_SIZE // 2, _SIZE // 2))
    return r, g, b


def _brightest(surface: pygame.Surface) -> int:
    return int(pygame.surfarray.array3d(surface).max())


CENTRE = Vector2(_SIZE / 2, _SIZE / 2)
LEFT = Vector2(0, _SIZE / 2)
RIGHT = Vector2(_SIZE, _SIZE / 2)


def _draw(renderer: PygameBackend, shape: str, color: Color) -> None:
    if shape == "rect":
        renderer.draw_rect(Rect(0, 0, _SIZE, _SIZE), color)
    elif shape == "circle":
        renderer.draw_circle(CENTRE, _SIZE / 4, color)
    else:
        renderer.draw_line(LEFT, RIGHT, color, 5)


@pytest.mark.parametrize("shape", ["rect", "circle", "line"])
def test_a_translucent_shape_blends_over_the_world(shape: str) -> None:
    surface, renderer = _white()
    _draw(renderer, shape, Color(0, 0, 0, 128))
    r, g, b = _centre(surface)
    assert 120 <= r <= 135 and r == g == b


@pytest.mark.parametrize("shape", ["rect", "circle", "line"])
def test_an_opaque_shape_still_paints_over(shape: str) -> None:
    surface, renderer = _white()
    _draw(renderer, shape, Color(200, 10, 10))
    assert _centre(surface) == (200, 10, 10)


@pytest.mark.parametrize("shape", ["rect", "circle", "line"])
def test_a_fully_transparent_shape_draws_nothing(shape: str) -> None:
    surface, renderer = _white()
    _draw(renderer, shape, Color(0, 0, 0, 0))
    assert _centre(surface) == (255, 255, 255)


def test_a_translucent_outline_leaves_its_inside_alone() -> None:
    surface, renderer = _white()
    renderer.draw_rect(Rect(0, 0, _SIZE, _SIZE), Color(0, 0, 0, 128), 3)
    assert _centre(surface) == (255, 255, 255)
    r, _, _, _ = surface.get_at((1, _SIZE // 2))
    assert 120 <= r <= 135


def test_a_screen_flash_washes_over_the_world_instead_of_hiding_it() -> None:
    """The case that found it: a 70-alpha red flash, on the pygame backend."""
    surface, renderer = _white()
    flash = ScreenFlash()
    flash.trigger(Color(255, 0, 0, 70), duration=1.0)
    flash.render(renderer, Rect(0, 0, _SIZE, _SIZE))
    r, g, b = _centre(surface)
    assert r == 255
    assert 180 <= g <= 190 and g == b


def test_render_text_bakes_alpha_into_the_glyphs() -> None:
    font = pygame.font.Font(None, 30)
    solid = render_text(font, "MM", (255, 255, 255, 255))
    half = render_text(font, "MM", (255, 255, 255, 128))
    gone = render_text(font, "MM", (255, 255, 255, 0))
    solid_alpha = pygame.surfarray.pixels_alpha(solid).astype(int)
    half_alpha = pygame.surfarray.pixels_alpha(half).astype(int)
    assert solid_alpha.max() == 255
    assert 126 <= half_alpha.max() <= 129
    # Antialiased edges stay in proportion rather than turning solid.
    edge = (solid_alpha > 0) & (solid_alpha < 255)
    assert edge.any()
    assert np.all(np.abs(half_alpha[edge] - solid_alpha[edge] * 128 / 255) <= 1.5)
    assert pygame.surfarray.pixels_alpha(gone).max() == 0


def test_render_text_keeps_the_colour() -> None:
    font = pygame.font.Font(None, 30)
    text = render_text(font, "MM", (200, 40, 10, 128))
    rgb = pygame.surfarray.pixels3d(text)
    alpha = pygame.surfarray.pixels_alpha(text)
    full = alpha == alpha.max()
    assert tuple(rgb[full][0]) == (200, 40, 10)


def test_faded_world_text_is_dimmer() -> None:
    surface, renderer = _black()
    renderer.draw_text("MM", Vector2(4, 4), Color(255, 255, 255, 255), 30)
    solid = _brightest(surface)
    surface, renderer = _black()
    renderer.draw_text("MM", Vector2(4, 4), Color(255, 255, 255, 64), 30)
    faded = _brightest(surface)
    surface, renderer = _black()
    renderer.draw_text("MM", Vector2(4, 4), Color(255, 255, 255, 0), 30)
    assert solid == 255
    assert 60 <= faded <= 68
    assert _brightest(surface) == 0


def test_faded_ui_text_is_dimmer() -> None:
    surface = pygame.Surface((_SIZE, _SIZE))
    surface.fill((0, 0, 0))
    PygameUIRenderer(surface).draw_text(
        "MM", Vector2(4, 4), Color(255, 255, 255, 64), 30
    )
    assert 60 <= _brightest(surface) <= 68


def test_faded_text_on_the_gpu_is_dimmer(wgpu_frame: Any) -> None:
    from pyguara.graphics.backends.wgpu import WgpuRenderer

    brightest = []
    for alpha in (255, 64):
        frame = wgpu_frame(_SIZE, _SIZE)
        frame.gpu.clear(0, 0, 0, 255)
        WgpuRenderer(frame).draw_text(
            "MM", Vector2(4, 4), Color(255, 255, 255, alpha), 30
        )
        frame.gpu.end_frame()
        pixels = np.frombuffer(frame.gpu.read_pixels(), dtype=np.uint8)
        brightest.append(int(pixels.reshape(-1, 4)[:, :3].max()))
    assert brightest[0] >= 250
    assert 55 <= brightest[1] <= 70
