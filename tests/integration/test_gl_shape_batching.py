"""Shape type, not submission order, decides what covers what.

`ModernGLRenderer` buckets shape instances by type and issues one
instanced draw call per bucket at `end_frame()` -- every rectangle, then
every circle, then every line. Within a single flush that makes the
ordering **by type**: a circle drawn first still lands on top of a
rectangle drawn after it.

It is easy to be bitten by and hard to see: `games/guara_falcao` drew its
parallax trees before the platforms in front of them, and the canopies
(circles) covered the platforms (rectangles) anyway. The frame renders, it
just renders the wrong thing in front.

`end_frame()` is therefore a depth boundary as much as a flush, and the
demo calls it once per layer. These tests pin the property that makes that
necessary -- if the backend ever becomes order-preserving, they fail, and
whoever changed it can go and delete the flushes.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer

pytestmark = pytest.mark.integration

_SIZE = 64
RED = Color(255, 0, 0)
BLUE = Color(0, 0, 255)


@pytest.fixture
def scene(gl_ctx: Any):
    """A framebuffer and a renderer drawing into it."""
    fbo = gl_ctx.simple_framebuffer((_SIZE, _SIZE))
    fbo.use()
    renderer = ModernGLRenderer(gl_ctx, _SIZE, _SIZE)
    try:
        yield fbo, renderer
    finally:
        renderer.release()
        fbo.release()


def _centre(fbo: Any) -> tuple[int, int, int]:
    """Read the centre pixel back as an `(r, g, b)` triple."""
    raw = np.frombuffer(fbo.read(components=3), dtype=np.uint8)
    image = raw.reshape((_SIZE, _SIZE, 3))
    return tuple(int(c) for c in image[_SIZE // 2, _SIZE // 2])  # type: ignore[return-value]


def test_a_circle_covers_a_rectangle_submitted_after_it(scene: Any) -> None:
    """The surprise: submission order does not win."""
    fbo, renderer = scene
    renderer.clear((0, 0, 0, 255))

    renderer.draw_circle(Vector2(_SIZE / 2, _SIZE / 2), _SIZE / 3, BLUE)
    renderer.draw_rect(Rect(0, 0, _SIZE, _SIZE), RED)
    renderer.end_frame()

    assert _centre(fbo) == (0, 0, 255)


def test_a_flush_between_them_restores_the_order(scene: Any) -> None:
    """Which is what makes `end_frame()` a usable depth boundary."""
    fbo, renderer = scene
    renderer.clear((0, 0, 0, 255))

    renderer.draw_circle(Vector2(_SIZE / 2, _SIZE / 2), _SIZE / 3, BLUE)
    renderer.end_frame()
    renderer.draw_rect(Rect(0, 0, _SIZE, _SIZE), RED)
    renderer.end_frame()

    assert _centre(fbo) == (255, 0, 0)


def test_within_one_bucket_submission_order_holds(scene: Any) -> None:
    """Two rectangles do behave the way anyone would expect."""
    fbo, renderer = scene
    renderer.clear((0, 0, 0, 255))

    renderer.draw_rect(Rect(0, 0, _SIZE, _SIZE), BLUE)
    renderer.draw_rect(Rect(0, 0, _SIZE, _SIZE), RED)
    renderer.end_frame()

    assert _centre(fbo) == (255, 0, 0)
