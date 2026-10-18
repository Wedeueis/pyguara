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

from typing import Any

import numpy as np
import pytest

from pyguara.common.types import Color, Rect
from pyguara.graphics.backends.moderngl.blend import (
    DEFAULT_BLEND_MODE,
    apply_blend_mode,
)
from pyguara.graphics.backends.moderngl.ui_renderer import GLUIRenderer

pytestmark = pytest.mark.integration

_SIZE = 64
_CENTRE = _SIZE // 2


@pytest.fixture
def blended_ctx(gl_ctx: Any) -> Any:
    """The shared GL context with alpha blending set up.

    `GLUIRenderer` draws without a `ModernGLRenderer`, so nothing has
    applied the engine's blend mode -- and a UI renderer whose panels do
    not blend reads back nothing like what it draws. This applies the same
    mode the renderer would, from the same source, rather than repeating
    the factor pair here.

    Args:
        gl_ctx: The session's standalone context.

    Returns:
        The same context, with blending enabled.
    """
    apply_blend_mode(gl_ctx, DEFAULT_BLEND_MODE)
    return gl_ctx


def render_ui(ctx: Any, draw) -> tuple[int, int, int]:
    """Run `draw` against a UI renderer and read back the centre pixel.

    Args:
        ctx: The GL context, with blending already set up.
        draw: Callable taking the `GLUIRenderer`.

    Returns:
        The centre pixel as an `(r, g, b)` triple.
    """
    import pygame

    if not pygame.get_init():
        pygame.init()

    fbo = ctx.simple_framebuffer((_SIZE, _SIZE))
    fbo.use()
    ctx.clear(0.0, 0.0, 0.0, 1.0)
    renderer = GLUIRenderer(ctx, _SIZE, _SIZE)
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


def test_a_ui_rect_keeps_its_channel_order(blended_ctx: Any) -> None:
    """Red stays red. The defect this pins swapped it with blue, turning
    Protocolo Bandeira's brown menu buttons into blue ones -- which nobody
    saw, because nothing could capture the UI layer.
    """
    pixel = render_ui(
        blended_ctx,
        lambda ui: ui.draw_rect(Rect(0, 0, _SIZE, _SIZE), Color(200, 30, 10)),
    )

    assert pixel == (200, 30, 10)


def test_blue_is_not_silently_red(blended_ctx: Any) -> None:
    """The mirror of the test above: a swap passes one of these and fails
    the other only if both are checked."""
    pixel = render_ui(
        blended_ctx,
        lambda ui: ui.draw_rect(Rect(0, 0, _SIZE, _SIZE), Color(10, 30, 200)),
    )

    assert pixel == (10, 30, 200)


def test_a_grey_rect_survives_unchanged(blended_ctx: Any) -> None:
    """A control: grey is symmetric under a red/blue swap, so it passes
    either way. It is here to prove the harness itself is not the thing
    producing the right answer."""
    pixel = render_ui(
        blended_ctx,
        lambda ui: ui.draw_rect(Rect(0, 0, _SIZE, _SIZE), Color(128, 128, 128)),
    )

    assert pixel == (128, 128, 128)


def test_the_overlay_composites_where_it_is_bound(blended_ctx: Any) -> None:
    """What `agent_view` relies on: `present()` draws into the currently
    bound framebuffer, so a capture can aim it at a buffer it can read
    rather than at the unreadable default one."""
    pixel = render_ui(
        blended_ctx,
        lambda ui: ui.draw_rect(Rect(0, 0, _SIZE, _SIZE), Color(0, 255, 0)),
    )

    assert pixel == (0, 255, 0)


def test_nothing_drawn_leaves_the_target_alone(blended_ctx: Any) -> None:
    """An idle frame must not paint over what the render graph produced."""
    pixel = render_ui(blended_ctx, lambda ui: None)

    assert pixel == (0, 0, 0)


def test_a_translucent_fill_blends_instead_of_punching_a_hole(
    blended_ctx: Any,
) -> None:
    """The overlay surface is `SRCALPHA`, and `pygame.draw` replaces the
    destination pixel including its alpha rather than compositing into it.

    So a half-transparent fill drawn over UI that is already there *erased*
    it, and the world showed through the hole. A ghost-skinned button --
    transparent fill, border only -- made this visible: it showed the game
    running behind the options panel it was sitting on.
    """
    pixel = render_ui(
        blended_ctx,
        lambda ui: (
            ui.draw_rect(Rect(0, 0, _SIZE, _SIZE), Color(200, 40, 40)),
            ui.draw_rect(Rect(0, 0, _SIZE, _SIZE), Color(0, 0, 0, 128)),
        ),
    )

    # Half black over opaque red: dimmed, not a hole through to the clear.
    assert pixel == pytest.approx((100, 20, 20), abs=3)


def _render_frame(ctx: Any, draw, size: int = 64, renderer: Any = None) -> Any:
    """Run `draw`, present, and read the whole framebuffer back.

    Rows come back **bottom-up**, as `glReadPixels` gives them: row 0 is
    the bottom of the screen. Left as-is rather than flipped here, because
    the orientation is exactly what the callers below are checking and a
    helper that quietly corrected it would make them pass either way.

    Args:
        ctx: The GL context, with blending already set up.
        draw: Callable taking the `GLUIRenderer`.
        size: Framebuffer edge in pixels.
        renderer: An existing renderer to draw through; one is made and
            released here when it is None.

    Returns:
        A `(size, size, 4)` uint8 array, bottom row first.
    """
    import pygame

    if not pygame.get_init():
        pygame.init()

    fbo = ctx.simple_framebuffer((size, size))
    fbo.use()
    ctx.clear(0.0, 0.0, 0.0, 1.0)
    own = renderer is None
    target = GLUIRenderer(ctx, size, size) if own else renderer
    try:
        draw(target)
        fbo.use()
        target.present()
        raw = np.frombuffer(fbo.read(components=4), dtype=np.uint8)
        return raw.reshape((size, size, 4)).copy()
    finally:
        if own:
            target.release()
        fbo.release()


def _corners(ctx: Any, renderer: Any = None) -> dict[str, tuple[int, ...]]:
    """Draw a frame that is asymmetric in both axes and sample four edges."""
    size = 64

    def draw(r: Any) -> None:
        r.draw_rect(Rect(0, 0, size, 8), Color(255, 0, 0, 255))  # top
        r.draw_rect(Rect(0, size - 8, size, 8), Color(0, 0, 255, 255))  # bottom
        r.draw_rect(Rect(0, 24, 8, 16), Color(0, 255, 0, 255))  # left
        r.draw_rect(Rect(size - 8, 24, 8, 16), Color(255, 255, 0, 255))  # right

    image = _render_frame(ctx, draw, size, renderer)
    middle = size // 2
    return {
        "top": tuple(int(c) for c in image[size - 1, middle]),
        "bottom": tuple(int(c) for c in image[0, middle]),
        "left": tuple(int(c) for c in image[size - 1 - 32, 4]),
        "right": tuple(int(c) for c in image[size - 1 - 32, size - 4]),
    }


class TestTheOverlayIsNotUpsideDownOrMirrored:
    """`present()` stopped flipping the surface on the CPU -- the quad's
    `v` runs 1 at the bottom of the screen instead, so the sampler does
    it. A flip is exactly the kind of change that a centre-pixel test
    cannot see: every existing assertion in this module samples the middle
    of a symmetric shape, where upside-down and right-way-up agree.

    These sample four edges of a frame that is asymmetric in both axes, so
    a lost flip, a doubled flip or a horizontal mirror each show up as a
    swapped pair rather than as nothing.
    """

    def test_the_top_of_the_surface_is_the_top_of_the_screen(
        self, blended_ctx: Any
    ) -> None:
        edges = _corners(blended_ctx)

        assert edges["top"][:3] == (255, 0, 0)
        assert edges["bottom"][:3] == (0, 0, 255)

    def test_it_is_not_mirrored_horizontally(self, blended_ctx: Any) -> None:
        """A `u` flip would pass the vertical test above and still be
        wrong."""
        edges = _corners(blended_ctx)

        assert edges["left"][:3] == (0, 255, 0)
        assert edges["right"][:3] == (255, 255, 0)


class TestTheOverlaySurvivesAResize:
    """`resize()` replaces the texture, and used to build a bare one --
    losing both the LINEAR filter and the swizzle that the original was
    given. That was harmless only while the swizzle happened to equal the
    default; the upload depends on it now, so a resized window would have
    rendered every UI colour with red and blue swapped.
    """

    def test_colours_and_orientation_hold_after_a_resize(
        self, blended_ctx: Any
    ) -> None:
        import pygame

        if not pygame.get_init():
            pygame.init()
        renderer = GLUIRenderer(blended_ctx, 32, 32)
        try:
            renderer.resize(64, 64)
            edges = _corners(blended_ctx, renderer)
        finally:
            renderer.release()

        assert edges["top"][:3] == (255, 0, 0)
        assert edges["bottom"][:3] == (0, 0, 255)
        assert edges["left"][:3] == (0, 255, 0)

    def test_the_replacement_texture_keeps_its_settings(self, blended_ctx: Any) -> None:
        """Stated on the texture as well as through the pixels: the pixel
        test above would also pass if the default swizzle happened to be
        right, which is precisely how this survived the first time."""
        renderer = GLUIRenderer(blended_ctx, 32, 32)
        try:
            before = (renderer._texture.swizzle, renderer._texture.filter)
            renderer.resize(64, 64)

            assert (renderer._texture.swizzle, renderer._texture.filter) == before
        finally:
            renderer.release()


class TestTheFrameIsNotCopiedOnTheWayToTheGpu:
    """The upload is the surface's own memory. Two full-surface CPU copies
    stood in front of it -- a `pygame.transform.flip` and a
    `pygame.image.tobytes` conversion to RGBA -- together 3.3 ms a frame
    at 1280x720 and 12.3 ms at 1920x1080, paid whether the UI drew one
    label or a whole HUD. Both are gone; this is what stops them coming
    back one well-meaning refactor at a time.
    """

    def test_present_hands_gl_the_surfaces_own_buffer(
        self, blended_ctx: Any, monkeypatch: Any
    ) -> None:
        import pygame

        if not pygame.get_init():
            pygame.init()

        calls: list[str] = []
        monkeypatch.setattr(
            pygame.transform,
            "flip",
            lambda *a, **k: calls.append("flip"),  # type: ignore[arg-type]
        )
        monkeypatch.setattr(
            pygame.image,
            "tobytes",
            lambda *a, **k: calls.append("tobytes"),  # type: ignore[arg-type]
        )

        renderer = GLUIRenderer(blended_ctx, 32, 32)
        try:
            renderer.draw_rect(Rect(0, 0, 32, 32), Color(255, 0, 0, 255))
            renderer.present()
        finally:
            renderer.release()

        assert calls == []

    def test_the_fallback_still_agrees_with_the_fast_path(
        self, blended_ctx: Any
    ) -> None:
        """A surface whose rows are padded cannot be uploaded raw, so
        `_pixels` converts instead -- and the conversion has to produce
        the same byte order the swizzle is set for, or it swaps red and
        blue on exactly the frames nobody looks at."""
        import pygame

        if not pygame.get_init():
            pygame.init()
        renderer = GLUIRenderer(blended_ctx, 32, 32)
        try:
            renderer.draw_rect(Rect(0, 0, 32, 32), Color(10, 20, 200, 255))
            raw = bytes(renderer._pixels())
            # Force the fallback by making the pitch disagree with the width.
            renderer._width = 31
            converted = bytes(renderer._pixels())
        finally:
            renderer.release()

        assert converted == raw
