"""Real-GL pixel readback for the ModernGL UI overlay.

The UI layer went unwatched for as long as it existed. `agent_view`
captures the buffer the final pass blits from, and `Application`
composites the UI onto the default framebuffer *after* that -- so no
`UIManager` widget in any demo had ever appeared in a capture, and a
channel-order bug in this renderer survived untouched: it uploaded RGBA
bytes and told GL to read them as BGRA, so every UI colour came out with
red and blue swapped.

Nothing but a pixel readback catches that. A mock records the call and a
headless run records nothing at all, and both pass while the menu renders
in the wrong colours.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

from pyguara.common.types import Color, Rect
from pyguara.graphics.backends.moderngl.ui_renderer import GLUIRenderer

pytestmark = pytest.mark.integration

_SIZE = 64
_CENTRE = _SIZE // 2


@pytest.fixture(scope="module")
def gl_ctx() -> Iterator[Any]:
    """A standalone GL context, or a skip on a machine without one."""
    moderngl = pytest.importorskip("moderngl")
    try:
        ctx = moderngl.create_standalone_context()
    except Exception as exc:  # pragma: no cover - depends on the machine
        pytest.skip(f"no standalone GL context available: {exc}")

    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA
    try:
        yield ctx
    finally:
        ctx.release()


def render_ui(gl_ctx: Any, draw) -> tuple[int, int, int]:
    """Run `draw` against a UI renderer and read back the centre pixel.

    Args:
        gl_ctx: The GL context.
        draw: Callable taking the `GLUIRenderer`.

    Returns:
        The centre pixel as an `(r, g, b)` triple.
    """
    import pygame

    if not pygame.get_init():
        pygame.init()

    fbo = gl_ctx.simple_framebuffer((_SIZE, _SIZE))
    fbo.use()
    gl_ctx.clear(0.0, 0.0, 0.0, 1.0)
    renderer = GLUIRenderer(gl_ctx, _SIZE, _SIZE)
    try:
        draw(renderer)
        # The overlay composites into whatever framebuffer is bound, which
        # is what lets `agent_view` aim it at the buffer it can read.
        fbo.use()
        renderer.present()
        raw = np.frombuffer(fbo.read(components=3), dtype=np.uint8)
        image = raw.reshape((_SIZE, _SIZE, 3))
        return tuple(int(c) for c in image[_CENTRE, _CENTRE])  # type: ignore[return-value]
    finally:
        renderer.release()
        fbo.release()


def test_a_ui_rect_keeps_its_channel_order(gl_ctx: Any) -> None:
    """Red stays red. The defect this pins swapped it with blue, turning
    Protocolo Bandeira's brown menu buttons into blue ones -- which nobody
    saw, because nothing could capture the UI layer.
    """
    pixel = render_ui(
        gl_ctx,
        lambda ui: ui.draw_rect(Rect(0, 0, _SIZE, _SIZE), Color(200, 30, 10)),
    )

    assert pixel == (200, 30, 10)


def test_blue_is_not_silently_red(gl_ctx: Any) -> None:
    """The mirror of the test above: a swap passes one of these and fails
    the other only if both are checked."""
    pixel = render_ui(
        gl_ctx,
        lambda ui: ui.draw_rect(Rect(0, 0, _SIZE, _SIZE), Color(10, 30, 200)),
    )

    assert pixel == (10, 30, 200)


def test_a_grey_rect_survives_unchanged(gl_ctx: Any) -> None:
    """A control: grey is symmetric under a red/blue swap, so it passes
    either way. It is here to prove the harness itself is not the thing
    producing the right answer."""
    pixel = render_ui(
        gl_ctx,
        lambda ui: ui.draw_rect(Rect(0, 0, _SIZE, _SIZE), Color(128, 128, 128)),
    )

    assert pixel == (128, 128, 128)


def test_the_overlay_composites_where_it_is_bound(gl_ctx: Any) -> None:
    """What `agent_view` relies on: `present()` draws into the currently
    bound framebuffer, so a capture can aim it at a buffer it can read
    rather than at the unreadable default one."""
    pixel = render_ui(
        gl_ctx,
        lambda ui: ui.draw_rect(Rect(0, 0, _SIZE, _SIZE), Color(0, 255, 0)),
    )

    assert pixel == (0, 255, 0)


def test_nothing_drawn_leaves_the_target_alone(gl_ctx: Any) -> None:
    """An idle frame must not paint over what the render graph produced."""
    pixel = render_ui(gl_ctx, lambda ui: None)

    assert pixel == (0, 0, 0)
