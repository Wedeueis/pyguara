"""Shapes and text draw in the order the caller asked for.

`ModernGLRenderer` queues `draw_rect`/`draw_circle`/`draw_line` and issues
them as instanced draws, while `draw_text` and `draw_texture` draw
immediately. Queued shapes were only flushed at `end_frame()`, so every
shape in a frame landed on top of every glyph and sprite in it, however
early the shape had been queued: `quintal_cerrado`'s hover tooltip drew its
labels and then its own card swallowed them.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer

pytestmark = pytest.mark.integration

SIZE = (80, 40)
WHITE = Color(255, 255, 255)
RED = Color(200, 0, 0)


@pytest.fixture
def frame(gl_ctx: Any) -> Any:
    """Draw through a real renderer and count white (text) pixels."""
    fbo = gl_ctx.simple_framebuffer(SIZE)

    def _run(*calls: Any) -> int:
        fbo.use()
        renderer = ModernGLRenderer(gl_ctx, *SIZE)
        renderer.clear(Color(0, 0, 0))
        for call in calls:
            call(renderer)
        renderer.end_frame()
        pixels = np.frombuffer(fbo.read(components=3), dtype=np.uint8)
        pixels = pixels.reshape(SIZE[1], SIZE[0], 3)
        return int(((pixels[:, :, 0] > 200) & (pixels[:, :, 1] > 200)).sum())

    yield _run
    fbo.release()


def _text(renderer: ModernGLRenderer) -> None:
    renderer.draw_text("HELLO", Vector2(5, 10), WHITE, 16)


def _cover(renderer: ModernGLRenderer) -> None:
    renderer.draw_rect(Rect(0, 0, *SIZE), RED)


def test_text_drawn_after_a_shape_sits_on_top_of_it(frame: Any) -> None:
    assert frame(_cover, _text) > 0


def test_text_drawn_before_a_covering_shape_stays_hidden(frame: Any) -> None:
    """The other half of ordering: later really does mean on top."""
    assert frame(_text, _cover) == 0
