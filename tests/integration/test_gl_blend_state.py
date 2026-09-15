"""The renderer owns the GL blend state, not the window.

`PygameGLWindow.open()` used to enable blending and pick the factor pair,
which meant a `ModernGLRenderer` over any other context drew unblended and
nothing said so -- every standalone-context fixture in this suite had to set
it up by hand, and `LightPass` restored the alpha pair from a remembered
constant because it had nothing to ask.

These tests deliberately use a context with **no** blend state configured, so
what they measure is what the renderer itself set up. They read pixels back
rather than the GL state: `moderngl` raises `NotImplementedError` on reading
`Context.blend_func`, and the pixels are the property that actually matters.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

from pyguara.graphics.backends.moderngl.blend import BlendMode, blending
from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer
from pyguara.graphics.types import RenderBatch

pytestmark = pytest.mark.integration

_SIZE = 64


@pytest.fixture
def bare_ctx() -> Iterator[Any]:
    """A standalone GL context with nothing set up on it.

    Function-scoped and unconfigured on purpose: the other GL fixtures in
    this suite enable blending themselves, which would mask exactly the
    thing under test.
    """
    moderngl = pytest.importorskip("moderngl")
    try:
        ctx = moderngl.create_standalone_context()
    except Exception as exc:  # pragma: no cover - depends on the machine
        pytest.skip(f"no standalone GL context available: {exc}")
    try:
        yield ctx
    finally:
        ctx.release()


class _HalfAlphaWhite:
    """A white texture at 50% alpha -- blended it reads grey, unblended white."""

    def __init__(self, ctx: Any, size: int = 16) -> None:
        pixel = b"\xff\xff\xff\x80"
        self._texture = ctx.texture((size, size), 4, pixel * (size * size))
        self._size = size

    @property
    def width(self) -> int:
        """Texture width in pixels."""
        return self._size

    @property
    def height(self) -> int:
        """Texture height in pixels."""
        return self._size

    @property
    def native_handle(self) -> Any:
        """The ModernGL texture the renderer binds."""
        return self._texture

    def release(self) -> None:
        """Drop the GL texture."""
        self._texture.release()


@pytest.fixture
def scene(bare_ctx: Any) -> Iterator[tuple[Any, ModernGLRenderer, _HalfAlphaWhite]]:
    """A framebuffer, a renderer drawing into it, and a half-alpha texture."""
    fbo = bare_ctx.simple_framebuffer((_SIZE, _SIZE))
    fbo.use()
    renderer = ModernGLRenderer(bare_ctx, _SIZE, _SIZE)
    texture = _HalfAlphaWhite(bare_ctx)
    try:
        yield fbo, renderer, texture
    finally:
        texture.release()
        renderer.release()
        fbo.release()


def _centre_pixel(fbo: Any) -> tuple[int, int, int]:
    """Read back the centre pixel as an (r, g, b) triple."""
    raw = np.frombuffer(fbo.read(components=3), dtype=np.uint8)
    image = raw.reshape((_SIZE, _SIZE, 3))
    return tuple(int(c) for c in image[_SIZE // 2, _SIZE // 2])  # type: ignore[return-value]


def _draw_half_alpha_quad(renderer: ModernGLRenderer, texture: _HalfAlphaWhite) -> None:
    """Clear to black, then draw the half-alpha white texture over it."""
    renderer.clear((0, 0, 0, 255))
    renderer.render_batch(
        RenderBatch(texture=texture, destinations=[(_SIZE / 2, _SIZE / 2)])
    )


# 0x80 / 255 of white over black, allowing for the driver's rounding.
BLENDED = 128
UNBLENDED = 255
TOLERANCE = 2


def test_a_renderer_blends_without_a_window_configuring_it(
    scene: tuple[Any, ModernGLRenderer, _HalfAlphaWhite],
) -> None:
    """The regression: nothing here enabled blending except the renderer.

    With the state back in `PygameGLWindow.open()`, this context has no
    blending at all and the quad reads back at full white.
    """
    fbo, renderer, texture = scene

    _draw_half_alpha_quad(renderer, texture)

    assert _centre_pixel(fbo) == pytest.approx((BLENDED,) * 3, abs=TOLERANCE)


def test_begin_frame_reasserts_the_default_mode(
    scene: tuple[Any, ModernGLRenderer, _HalfAlphaWhite],
    bare_ctx: Any,
) -> None:
    """A pass that leaves the context additive cannot bleed into next frame.

    Additive here would saturate the quad to white; alpha reads grey.
    """
    fbo, renderer, texture = scene
    moderngl = pytest.importorskip("moderngl")
    bare_ctx.blend_func = moderngl.ONE, moderngl.ONE

    renderer.begin_frame()
    _draw_half_alpha_quad(renderer, texture)

    assert _centre_pixel(fbo) == pytest.approx((BLENDED,) * 3, abs=TOLERANCE)


class TestBlendingContextManager:
    """What `LightPass` uses to take the context additive and give it back."""

    def test_the_block_selects_the_mode_it_was_given(
        self,
        scene: tuple[Any, ModernGLRenderer, _HalfAlphaWhite],
        bare_ctx: Any,
    ) -> None:
        fbo, renderer, texture = scene

        with blending(bare_ctx, BlendMode.ADDITIVE):
            _draw_half_alpha_quad(renderer, texture)

        assert _centre_pixel(fbo) == pytest.approx((UNBLENDED,) * 3, abs=TOLERANCE)

    def test_it_restores_the_default_afterwards(
        self,
        scene: tuple[Any, ModernGLRenderer, _HalfAlphaWhite],
        bare_ctx: Any,
    ) -> None:
        fbo, renderer, texture = scene

        with blending(bare_ctx, BlendMode.ADDITIVE):
            pass
        _draw_half_alpha_quad(renderer, texture)

        assert _centre_pixel(fbo) == pytest.approx((BLENDED,) * 3, abs=TOLERANCE)

    def test_it_restores_the_default_after_an_exception(
        self,
        scene: tuple[Any, ModernGLRenderer, _HalfAlphaWhite],
        bare_ctx: Any,
    ) -> None:
        fbo, renderer, texture = scene

        with pytest.raises(RuntimeError), blending(bare_ctx, BlendMode.ADDITIVE):
            raise RuntimeError("a pass blew up mid-draw")
        _draw_half_alpha_quad(renderer, texture)

        assert _centre_pixel(fbo) == pytest.approx((BLENDED,) * 3, abs=TOLERANCE)
