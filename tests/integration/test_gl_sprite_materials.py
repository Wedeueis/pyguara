"""`SpriteShader` materials on the ModernGL backend.

A `SpriteShader` is written for wgpu; its GLSL twin is what lets it run on
ModernGL until stage E retires that backend. These hold the twin to the
same standard the wgpu tests hold the WGSL: an identity material draws the
plain sprite, an inverting one draws the inverted texture. Without a twin,
the sprites are drawn plainly and the author is told once.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer
from pyguara.graphics.backends.moderngl.texture import GLTextureFactory
from pyguara.graphics.materials import Material, SpriteShader
from pyguara.graphics.pipeline.device import glsl
from pyguara.graphics.types import RenderBatch

pytestmark = pytest.mark.integration

_SIZE = 64

IDENTITY = SpriteShader(
    "identity",
    wgsl="fn material(sprite: Sprite) -> vec4<f32> {"
    " return textureSample(sprite_texture, sprite_sampler, sprite.uv) * sprite.color; }",
    glsl=glsl("sprite.frag"),
)

INVERT = SpriteShader(
    "invert",
    wgsl="fn material(sprite: Sprite) -> vec4<f32> {"
    " let t = textureSample(sprite_texture, sprite_sampler, sprite.uv);"
    " return vec4<f32>(1.0 - t.rgb, t.a) * sprite.color; }",
    glsl="""#version 330 core
in vec2 v_uv;
in vec4 v_color;
out vec4 frag_color;
uniform sampler2D u_texture;
void main() {
    vec4 t = texture(u_texture, v_uv);
    frag_color = vec4(1.0 - t.rgb, t.a) * v_color;
}
""",
)

WGSL_ONLY = SpriteShader(
    "wgsl_only",
    wgsl="fn material(sprite: Sprite) -> vec4<f32> { return vec4<f32>(1.0); }",
)


def _pixels(inverted: bool = False) -> bytes:
    """A 16x16 image with no symmetry, top row first."""
    rows = bytearray()
    for y in range(16):
        for x in range(16):
            r, g, b = (x * 16, y * 16, 200 if (x + y) % 3 else 40)
            if inverted:
                r, g, b = 255 - r, 255 - g, 255 - b
            rows += bytes((r, g, b, 255))
    return bytes(rows)


def render(
    gl_ctx: Any,
    material: Material | None,
    inverted: bool = False,
    renderer: ModernGLRenderer | None = None,
) -> np.ndarray:
    """Draw a turned, scaled, tinted batch into a framebuffer and read it."""
    factory = GLTextureFactory(gl_ctx)
    texture = factory.create_from_bytes("t", _pixels(inverted), 16, 16)
    target = gl_ctx.simple_framebuffer((_SIZE, _SIZE))
    target.use()
    target.clear(0.1, 0.2, 0.3, 1.0)
    renderer = renderer or ModernGLRenderer(gl_ctx, _SIZE, _SIZE)
    renderer.render_batch(
        RenderBatch(
            texture,
            [(10.0, 12.0), (40.0, 30.0)],
            rotations=[0.0, 30.0],
            scales=[(1.5, 1.5), (1.0, -1.0)],
            transforms_enabled=True,
            colors=[(255, 255, 255, 255), (255, 128, 0, 200)],
            colors_enabled=True,
            material=material,
        )
    )
    renderer.end_frame()
    return np.frombuffer(target.read(components=4), dtype=np.uint8).copy()


def test_an_identity_twin_draws_the_plain_sprite(gl_ctx: Any) -> None:
    plain = render(gl_ctx, None)

    background = np.array([26, 51, 76, 255], dtype=np.uint8)
    assert (plain.reshape(-1, 4) != background).any(axis=1).sum() > 200
    assert np.array_equal(render(gl_ctx, Material(IDENTITY)), plain)


def test_an_inverting_twin_draws_the_inverted_texture(gl_ctx: Any) -> None:
    assert np.array_equal(
        render(gl_ctx, Material(INVERT)), render(gl_ctx, None, inverted=True)
    )


def test_without_a_twin_the_sprite_is_drawn_plainly_and_said_once(
    gl_ctx: Any, caplog: pytest.LogCaptureFixture
) -> None:
    # Once per renderer, which is once per game.
    renderer = ModernGLRenderer(gl_ctx, _SIZE, _SIZE)
    with caplog.at_level("WARNING"):
        first = render(gl_ctx, Material(WGSL_ONLY), renderer=renderer)
        render(gl_ctx, Material(WGSL_ONLY), renderer=renderer)

    assert np.array_equal(first, render(gl_ctx, None))
    assert sum("wgsl_only" in r.getMessage() for r in caplog.records) == 1
