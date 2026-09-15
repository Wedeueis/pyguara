"""A material assigned to a batch must change what the GPU draws.

`Material` reached `RenderQueue` and `Batcher`, which sort and break batches
by `material_id`, but `ModernGLRenderer.render_batch()` never read
`RenderBatch.material` -- it drew every batch through its own sprite program.
Assigning a custom shader therefore changed nothing except costing a batch
break, and nothing in the suite could tell, because a mock context records
the calls without running them.

So these tests render into a real framebuffer through a standalone context
and read the pixels back, the way `test_moderngl_pixels.py` does for the
per-instance tint. The textures are white on purpose: a shader that ignores
them is visible immediately.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np
import pytest

from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer
from pyguara.graphics.materials.defaults import DEFAULT_SPRITE_VERTEX
from pyguara.graphics.materials.material import Material
from pyguara.graphics.materials.shader import Shader, ShaderCache
from pyguara.graphics.types import RenderBatch

pytestmark = pytest.mark.integration

_SIZE = 64

# A fragment shader that ignores the sprite texture entirely. If the batch's
# material is honoured the quad is solid green; if it is not, the default
# sprite shader draws the white texture and the pixel comes back white.
GREEN_FRAGMENT = """
#version 330 core
in vec2 v_uv;
in vec4 v_color;
out vec4 f_color;
void main() { f_color = vec4(0.0, 1.0, 0.0, 1.0); }
"""

UNIFORM_FRAGMENT = """
#version 330 core
in vec2 v_uv;
in vec4 v_color;
out vec4 f_color;
uniform vec3 u_ink;
void main() { f_color = vec4(u_ink, 1.0); }
"""

# Red from unit 0, green from unit 1. Only a red batch texture on unit 0 and
# a green material texture on unit 1 give yellow: sample both from either one
# and the result is that texture's own colour.
SECOND_SAMPLER_FRAGMENT = """
#version 330 core
in vec2 v_uv;
in vec4 v_color;
out vec4 f_color;
uniform sampler2D u_texture;
uniform sampler2D u_material_texture;
void main() {
    f_color = vec4(
        texture(u_texture, v_uv).r,
        texture(u_material_texture, v_uv).g,
        0.0,
        1.0
    );
}
"""

# Declares none of the per-instance attributes the renderer packs.
NAKED_VERTEX = """
#version 330 core
out vec2 v_uv;
out vec4 v_color;
void main() {
    v_uv = vec2(0.0);
    v_color = vec4(1.0);
    gl_Position = vec4(0.0, 0.0, 0.0, 1.0);
}
"""


class _SolidTexture:
    """A single-colour opaque texture, wrapped as the renderer expects."""

    def __init__(self, ctx: Any, rgb: tuple[int, int, int], size: int = 16) -> None:
        pixel = bytes(rgb) + b"\xff"
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
def scene(gl_ctx: Any) -> Iterator[tuple[Any, ModernGLRenderer, _SolidTexture]]:
    """A framebuffer, a renderer drawing into it, and a white texture."""
    fbo = gl_ctx.simple_framebuffer((_SIZE, _SIZE))
    fbo.use()
    renderer = ModernGLRenderer(gl_ctx, _SIZE, _SIZE)
    texture = _SolidTexture(gl_ctx, (255, 255, 255))
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


def _material(ctx: Any, name: str, fragment: str, **kwargs: Any) -> Material:
    """A material over the default sprite vertex shader and `fragment`."""
    shader: Shader = ShaderCache(ctx).get_or_compile(
        name, DEFAULT_SPRITE_VERTEX, fragment
    )
    return Material(shader=shader, **kwargs)


def _batch(texture: _SolidTexture, material: Material | None, count: int = 1):
    """A batch of `count` sprites at the centre of the framebuffer."""
    return RenderBatch(
        texture=texture,
        destinations=[(_SIZE / 2, _SIZE / 2)] * count,
        material=material,
    )


class TestTheMaterialReachesTheGPU:
    def test_a_material_fragment_shader_replaces_the_sprite_shader(
        self, gl_ctx: Any, scene: tuple[Any, ModernGLRenderer, _SolidTexture]
    ) -> None:
        """The regression: green means the material drew, white means it did not."""
        fbo, renderer, texture = scene
        material = _material(gl_ctx, "green", GREEN_FRAGMENT)
        renderer.clear((0, 0, 0, 255))

        renderer.render_batch(_batch(texture, material))

        assert _centre_pixel(fbo) == (0, 255, 0)

    def test_a_material_uniform_reaches_the_shader(
        self, gl_ctx: Any, scene: tuple[Any, ModernGLRenderer, _SolidTexture]
    ) -> None:
        fbo, renderer, texture = scene
        material = _material(
            gl_ctx, "ink", UNIFORM_FRAGMENT, uniforms={"u_ink": (0.0, 0.0, 1.0)}
        )
        renderer.clear((0, 0, 0, 255))

        renderer.render_batch(_batch(texture, material))

        assert _centre_pixel(fbo) == (0, 0, 255)

    def test_a_uniform_the_shader_does_not_declare_is_ignored(
        self, gl_ctx: Any, scene: tuple[Any, ModernGLRenderer, _SolidTexture]
    ) -> None:
        """The same tolerance `Shader.set_uniform` has everywhere else."""
        fbo, renderer, texture = scene
        material = _material(
            gl_ctx, "green", GREEN_FRAGMENT, uniforms={"u_nonexistent": 1.0}
        )
        renderer.clear((0, 0, 0, 255))

        renderer.render_batch(_batch(texture, material))

        assert _centre_pixel(fbo) == (0, 255, 0)

    def test_the_batch_texture_still_owns_unit_zero(
        self, gl_ctx: Any, scene: tuple[Any, ModernGLRenderer, _SolidTexture]
    ) -> None:
        """A material's own texture is a second sampler, not a replacement.

        The shader takes red from unit 0 and green from unit 1, so yellow is
        reachable only if the batch's red texture and the material's green one
        landed on different units. Sampling either one twice gives that
        texture's own colour instead.
        """
        fbo, renderer, _ = scene
        red = _SolidTexture(gl_ctx, (255, 0, 0))
        green = _SolidTexture(gl_ctx, (0, 255, 0))
        material = _material(
            gl_ctx, "two_samplers", SECOND_SAMPLER_FRAGMENT, texture=green
        )
        renderer.clear((0, 0, 0, 255))

        try:
            renderer.render_batch(_batch(red, material))

            assert _centre_pixel(fbo) == (255, 255, 0)
        finally:
            red.release()
            green.release()


class TestTheDefaultPathIsUnchanged:
    def test_a_batch_without_a_material_draws_its_texture(
        self, scene: tuple[Any, ModernGLRenderer, _SolidTexture]
    ) -> None:
        fbo, renderer, texture = scene
        renderer.clear((0, 0, 0, 255))

        renderer.render_batch(_batch(texture, None))

        assert _centre_pixel(fbo) == (255, 255, 255)

    def test_a_material_batch_does_not_leak_into_the_next_batch(
        self, gl_ctx: Any, scene: tuple[Any, ModernGLRenderer, _SolidTexture]
    ) -> None:
        fbo, renderer, texture = scene
        material = _material(gl_ctx, "green", GREEN_FRAGMENT)
        renderer.clear((0, 0, 0, 255))

        renderer.render_batch(_batch(texture, material))
        renderer.render_batch(_batch(texture, None))

        assert _centre_pixel(fbo) == (255, 255, 255)


class TestGrowingTheInstanceBuffer:
    def test_a_material_still_draws_after_the_buffer_grows(
        self, gl_ctx: Any, scene: tuple[Any, ModernGLRenderer, _SolidTexture]
    ) -> None:
        """Every material VAO points at the instance buffer that was released.

        Without dropping them on growth, this draws through a vertex array
        over freed GPU memory -- which is not reliably an error, just wrong.
        """
        fbo, renderer, texture = scene
        material = _material(gl_ctx, "green", GREEN_FRAGMENT)

        renderer.render_batch(_batch(texture, material))
        renderer.render_batch(
            _batch(texture, None, count=ModernGLRenderer.INITIAL_CAPACITY + 1)
        )
        renderer.clear((0, 0, 0, 255))
        renderer.render_batch(_batch(texture, material))

        assert _centre_pixel(fbo) == (0, 255, 0)


class TestAVertexShaderThatIgnoresTheLayout:
    def test_it_raises_rather_than_drawing_nothing(
        self, gl_ctx: Any, scene: tuple[Any, ModernGLRenderer, _SolidTexture]
    ) -> None:
        """The instance layout is fixed, so a vertex shader has to honour it."""
        _, renderer, texture = scene
        shader = ShaderCache(gl_ctx).get_or_compile(
            "naked", NAKED_VERTEX, GREEN_FRAGMENT
        )

        with pytest.raises(ValueError, match="in_pos"):
            renderer.render_batch(_batch(texture, Material(shader=shader)))
