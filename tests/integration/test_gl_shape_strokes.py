"""An outlined shape draws every edge, inside its bounds, on a real GPU.

`shape.frag` used to centre a stroke on the shape's edge and keep pixels
with `abs(d) <= width / 2`. For a 1px border that puts every pixel centre
exactly on the band's boundary (d = +-0.5), so floating-point noise picked
which edges survived: on the machine this was found on, every horizontal
edge of `quintal_cerrado`'s grid vanished and only the vertical lines drew.

It also disagreed with the pygame backend, which draws a border *inside*
the rect -- so the same `draw_rect(rect, color, width=1)` landed half a
pixel apart on the two backends. The stroke band is now `[-width, 0]`,
inside the edge, like pygame's.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer

pytestmark = pytest.mark.integration

SIZE = 64
RED = Color(255, 0, 0)


@pytest.fixture
def draw(gl_ctx: Any) -> Any:
    """Draw through a real renderer and return the frame as a top-down array."""
    fbo = gl_ctx.simple_framebuffer((SIZE, SIZE))

    def _draw(*calls: Any) -> np.ndarray:
        fbo.use()
        renderer = ModernGLRenderer(gl_ctx, SIZE, SIZE)
        renderer.clear(Color(0, 0, 0))
        for call in calls:
            call(renderer)
        renderer.end_frame()
        pixels = np.frombuffer(fbo.read(components=3), dtype=np.uint8)
        # GL's origin is bottom-left; flip to the screen's top-left.
        return pixels.reshape(SIZE, SIZE, 3)[::-1]

    yield _draw
    fbo.release()


def _is_red(pixel: np.ndarray) -> bool:
    return bool(pixel[0] > 200 and pixel[1] < 50 and pixel[2] < 50)


@pytest.mark.parametrize("x, y", [(10, 10), (13, 17), (20, 31)])
def test_a_one_pixel_outline_draws_all_four_edges(draw: Any, x: int, y: int) -> None:
    frame = draw(lambda r: r.draw_rect(Rect(x, y, 20, 20), RED, width=1))

    mid_x, mid_y = x + 10, y + 10
    assert _is_red(frame[y, mid_x]), "top edge missing"
    assert _is_red(frame[y + 19, mid_x]), "bottom edge missing"
    assert _is_red(frame[mid_y, x]), "left edge missing"
    assert _is_red(frame[mid_y, x + 19]), "right edge missing"
    assert not _is_red(frame[mid_y, mid_x]), "an outline must not fill"


def test_an_outline_stays_inside_the_rect_like_the_pygame_backend(draw: Any) -> None:
    frame = draw(lambda r: r.draw_rect(Rect(10, 10, 20, 20), RED, width=2))

    assert _is_red(frame[20, 10]) and _is_red(frame[20, 11])
    assert not _is_red(frame[20, 9]), "stroke leaked outside the left edge"
    assert not _is_red(frame[9, 20]), "stroke leaked above the top edge"
    assert not _is_red(frame[20, 12]), "stroke is wider than 2px"


def test_a_filled_rect_covers_exactly_its_bounds(draw: Any) -> None:
    frame = draw(lambda r: r.draw_rect(Rect(10, 10, 20, 20), RED))

    assert _is_red(frame[10, 10]) and _is_red(frame[29, 29])
    assert not _is_red(frame[9, 20]) and not _is_red(frame[30, 20])


def test_a_circle_outline_is_a_ring_inside_its_radius(draw: Any) -> None:
    frame = draw(lambda r: r.draw_circle(Vector2(32, 32), 12, RED, width=2))

    assert _is_red(frame[32, 32 + 11]), "ring missing on the right"
    assert _is_red(frame[32 - 11, 32]), "ring missing at the top"
    assert not _is_red(frame[32, 32 + 13]), "ring leaked outside its radius"
    assert not _is_red(frame[32, 32]), "an outline must not fill"
