"""A line on ModernGL runs between its own endpoints.

`shape.vert` turned each shape by `mat2(c, -s, s, c)`, which rotates from +x
towards -y on a y-down screen, while every producer passes the angle the
other way -- `atan2(dy, dx)` in screen space, from `draw_line` and from the
spark pool. So every diagonal line came out mirrored about its centre: a
line from (10, 10) to (60, 60) was drawn through (15, 55). `true_coral`'s
snake, a tube of capsules along its spine, drew as a row of pills lying
across it. Found comparing the GL demos with wgpu, which draws lines itself.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from pyguara.common.types import Color, Vector2
from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer
from pyguara.graphics.types import ShapeBatch, ShapeKind

pytestmark = pytest.mark.integration

_SIZE = 72


def _draw(gl_ctx: Any, draw: Any) -> np.ndarray:
    """Run `draw` on a ModernGL renderer and return the frame, top row first."""
    target = gl_ctx.simple_framebuffer((_SIZE, _SIZE))
    target.use()
    target.clear(0.0, 0.0, 0.0, 1.0)
    renderer = ModernGLRenderer(gl_ctx, _SIZE, _SIZE)
    draw(renderer)
    renderer.end_frame()
    raw = np.frombuffer(target.read(components=3), dtype=np.uint8)
    return np.flipud(raw.reshape((_SIZE, _SIZE, 3)))


def _lit(image: np.ndarray, x: int, y: int) -> bool:
    return bool(image[y, x].max() > 100)


@pytest.mark.parametrize(
    ("start", "end", "on", "off"),
    [
        ((10, 10), (60, 60), (15, 15), (15, 55)),  # down and right
        ((10, 60), (60, 10), (15, 55), (15, 15)),  # up and right
    ],
)
def test_a_diagonal_line_runs_between_its_endpoints(
    gl_ctx: Any, start: Any, end: Any, on: Any, off: Any
) -> None:
    image = _draw(
        gl_ctx,
        lambda r: r.draw_line(Vector2(*start), Vector2(*end), Color(255, 255, 255), 4),
    )

    assert _lit(image, *on)
    assert not _lit(image, *off)


def test_a_batched_line_turns_the_way_its_angle_says(gl_ctx: Any) -> None:
    """A spark streak's row, as the pool packs one: atan2 in screen space."""
    angle = math.atan2(50, 50)
    row = [35, 35, 35.0 + 2, 2.0, angle, 1.0, 1.0, 1.0, 1.0, 0.0, 2.0]
    image = _draw(gl_ctx, lambda r: r.render_shapes(ShapeBatch(ShapeKind.LINE, [row])))

    assert _lit(image, 15, 15)
    assert not _lit(image, 15, 55)
