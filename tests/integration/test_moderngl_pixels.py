"""Real-GL pixel readback for the instanced sprite path.

`test_moderngl_backend.py` drives the renderer against a `MagicMock`
context: it proves the calls are made and the arguments are shaped right,
but a mock cannot tell you what the GPU did with them. The per-instance
tint is exactly the kind of change a mock test cannot see -- the previous
layout packed no colour at all, and every one of those tests passed.

So this module renders into a real framebuffer through a standalone
context and reads the pixels back. It is deliberately the mirror of
`test_graphics_backend.py::test_render_batch_tint_multiplies_the_actual_pixels`:
same shape, near-enough the same name, a white texture tinted red. Parity
between the two backends is then something you can see by reading them
side by side.

Two cases only -- untinted and tinted. This is not the seed of a general
image-diff suite; those go flaky, and the shared-state bugs they would
catch are cheaper to catch in `instancing.py`'s unit tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

from pyguara.common.types import Vector2
from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer
from pyguara.graphics.components.camera import Camera2D
from pyguara.graphics.components.particles import ParticleSystem
from pyguara.graphics.types import RenderBatch

pytestmark = pytest.mark.integration

_SIZE = 64


class _WhiteTexture:
    """An opaque white GL texture, wrapped as the renderer expects."""

    def __init__(self, ctx: Any, size: int = 16) -> None:
        self._texture = ctx.texture((size, size), 4, b"\xff" * (size * size * 4))
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
def scene(gl_ctx: Any) -> Iterator[tuple[Any, ModernGLRenderer, _WhiteTexture]]:
    """A framebuffer, a renderer drawing into it, and a white texture."""
    fbo = gl_ctx.simple_framebuffer((_SIZE, _SIZE))
    fbo.use()
    renderer = ModernGLRenderer(gl_ctx, _SIZE, _SIZE)
    texture = _WhiteTexture(gl_ctx)
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


def test_an_untinted_batch_renders_the_texture_unchanged(
    scene: tuple[Any, ModernGLRenderer, _WhiteTexture],
) -> None:
    """Without `colors_enabled`, a white texture stays white."""
    fbo, renderer, texture = scene
    renderer.clear((0, 0, 0, 255))

    renderer.render_batch(
        RenderBatch(
            texture=texture,
            destinations=[(_SIZE / 2, _SIZE / 2)],
        )
    )

    assert _centre_pixel(fbo) == (255, 255, 255)


def test_render_batch_tint_multiplies_the_actual_pixels(
    scene: tuple[Any, ModernGLRenderer, _WhiteTexture],
) -> None:
    """A red tint on a white texture must land as red pixels on the GPU.

    The direct mirror of the Pygame backend's test of the same name. Before
    the instance layout carried a colour, this was the failing half of that
    pair: the batch executed, and drew white.
    """
    fbo, renderer, texture = scene
    renderer.clear((0, 0, 0, 255))

    renderer.render_batch(
        RenderBatch(
            texture=texture,
            destinations=[(_SIZE / 2, _SIZE / 2)],
            colors=[(255, 0, 0, 255)],
            colors_enabled=True,
        )
    )

    assert _centre_pixel(fbo) == (255, 0, 0)


def test_a_tinted_particle_reaches_the_gpu_tinted(
    scene: tuple[Any, ModernGLRenderer, _WhiteTexture],
) -> None:
    """The round trip `ParticleSystem` needs: a coloured particle, through
    the batch it emits, to a red pixel.

    `ParticleSystem.render` has emitted `colors_enabled` batches all along.
    Under this backend they drew white, so a particle effect built and
    checked on Pygame lost its colour the moment the GL backend was
    selected -- silently, because nothing raised.
    """
    fbo, renderer, texture = scene
    renderer.clear((0, 0, 0, 255))

    particles = ParticleSystem(capacity=4)
    particles.emit(
        texture,
        Vector2(_SIZE / 2, _SIZE / 2),
        count=1,
        speed=0.0,
        life=1.0,
        color_start=(255, 0, 0, 255),
        color_end=(255, 0, 0, 255),
    )
    camera = Camera2D(_SIZE, _SIZE)
    camera.position = Vector2(_SIZE / 2, _SIZE / 2)
    particles.render(renderer, camera)

    assert _centre_pixel(fbo) == (255, 0, 0)
