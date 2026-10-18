"""Integration tests for ModernGL graphics backend."""

import inspect
import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.config.types import WindowConfig
from pyguara.graphics.backends.moderngl.loaders import GLTextureLoader
from pyguara.graphics.backends.moderngl.renderer import (
    _TEXT_CACHE_LIMIT,
    ModernGLRenderer,
)
from pyguara.graphics.backends.moderngl.texture import GLTexture
from pyguara.graphics.backends.moderngl.ui_renderer import GLUIRenderer

# ... imports ...
from pyguara.graphics.backends.moderngl.window import PygameGLWindow
from pyguara.graphics.types import RenderBatch

# Ensure headless execution for pygame parts
os.environ["SDL_VIDEODRIVER"] = "dummy"


@pytest.fixture
def mock_ctx() -> MagicMock:
    """Create a mock ModernGL context.

    Each call returns a fresh MagicMock rather than one shared instance --
    the renderer creates several independent buffers/VAOs/programs (sprite
    plus one per shape-type bucket), and tests need to tell them apart.
    """
    ctx = MagicMock()
    ctx.buffer.side_effect = lambda *args, **kwargs: MagicMock()
    ctx.program.side_effect = lambda *args, **kwargs: MagicMock()
    ctx.vertex_array.side_effect = lambda *args, **kwargs: MagicMock()
    ctx.texture.side_effect = lambda *args, **kwargs: MagicMock()
    return ctx


@pytest.fixture
def gl_window(mock_ctx: MagicMock) -> PygameGLWindow:
    """Create a PygameGLWindow with a mocked context."""
    with (
        patch("moderngl.create_context", return_value=mock_ctx),
        patch("pygame.display.set_mode"),
        patch("pygame.display.gl_set_attribute"),
    ):
        window = PygameGLWindow()
        config = WindowConfig(title="Test", screen_width=800, screen_height=600)
        window.open(config)
        return window


def test_window_initialization(gl_window: PygameGLWindow, mock_ctx: MagicMock) -> None:
    """Window should initialize OpenGL attributes and ModernGL context."""
    assert gl_window.width == 800
    assert gl_window.height == 600
    assert gl_window.get_screen() == mock_ctx


def test_the_window_leaves_the_blend_state_alone(mock_ctx: MagicMock) -> None:
    """Blending is the renderer's state; the window used to set it.

    A window that configured it would hide a renderer that did not -- which
    is exactly what happened: every standalone-context test had to enable
    blending by hand. See `test_gl_blend_state.py` for the pixel-level half.
    """
    with (
        patch("moderngl.create_context", return_value=mock_ctx),
        patch("pygame.display.set_mode"),
        patch("pygame.display.gl_set_attribute"),
    ):
        PygameGLWindow().open(
            WindowConfig(title="Test", screen_width=800, screen_height=600)
        )

    mock_ctx.enable.assert_not_called()
    assert "blend_func" not in mock_ctx.__dict__


def test_renderer_initialization(mock_ctx: MagicMock) -> None:
    """Renderer should compile shaders and create buffers."""

    # Mock file reading for shaders

    with patch("builtins.open", mock_open(read_data="shader source")):
        ModernGLRenderer(mock_ctx, 800, 600)

    # Sprite program + shape (rect/circle/line SDF) program.
    assert mock_ctx.program.call_count == 2

    assert mock_ctx.buffer.call_count >= 2  # Quad VBO + Instance VBO
    # Sprite VAO + one shape VAO per shape-type bucket (rect/circle/line).
    assert mock_ctx.vertex_array.call_count == 4


def test_render_batch(mock_ctx: MagicMock) -> None:
    """Renderer should pack batch data and draw."""
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    # Mock texture
    mock_gl_tex = MagicMock()
    texture = GLTexture("test.png", mock_gl_tex, 32, 32)

    batch = RenderBatch(
        texture=texture,
        destinations=[(10, 10), (20, 20)],
        rotations=[],
        scales=[],
        transforms_enabled=False,
    )

    # Capture the buffer write
    instance_vbo = renderer._instance_vbo

    renderer.render_batch(batch)

    # Verify data upload
    assert isinstance(instance_vbo, MagicMock)
    assert instance_vbo.write.called

    # Verify draw call
    # ModernGL render() takes mode as first arg, then instances as kwarg
    vao = renderer._vao
    assert isinstance(vao, MagicMock)

    vao.render.assert_called()
    call_args = vao.render.call_args
    # Check keyword arg 'instances'
    assert call_args.kwargs["instances"] == 2


def test_texture_loader(mock_ctx: MagicMock) -> None:
    """Loader should convert surface to bytes and upload."""
    loader = GLTextureLoader(mock_ctx)

    with patch("pygame.image.load") as mock_load:
        mock_surf = MagicMock()
        mock_surf.get_width.return_value = 100
        mock_surf.get_height.return_value = 100
        mock_surf.convert_alpha.return_value = mock_surf
        mock_load.return_value = mock_surf

        # No `pygame.transform.flip` patch: the loader does not flip any
        # more, and patching it away is what let the orientation bug sit
        # here unnoticed. See `test_gl_texture_orientation.py`.
        with patch("pygame.image.tobytes", return_value=b"pixeldata"):
            texture = loader.load("test.png")

        assert isinstance(texture, GLTexture)
        assert texture.width == 100
        mock_ctx.texture.assert_called_with((100, 100), 4, b"pixeldata")


# -- ModernGL shape shader (wayfinder ticket 25) --


def test_draw_rect_queues_and_flushes_at_end_frame(mock_ctx: MagicMock) -> None:
    """draw_rect is a no-op GPU-wise until end_frame() flushes its bucket."""
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    rect_vao = renderer._shape_vaos[renderer.SHAPE_TYPE_RECT]
    rect_vbo = renderer._shape_vbos[renderer.SHAPE_TYPE_RECT]

    renderer.draw_rect(Rect(10, 10, 20, 40), Color(255, 0, 0))
    rect_vao.render.assert_not_called()

    renderer.end_frame()

    assert rect_vbo.write.called
    rect_vao.render.assert_called_once()
    call_args = rect_vao.render.call_args
    assert call_args.kwargs["instances"] == 1

    # Buckets are one-shot -- a second end_frame() with nothing queued
    # issues no further draw call.
    rect_vao.render.reset_mock()
    renderer.end_frame()
    rect_vao.render.assert_not_called()


def test_draw_circle_and_line_use_their_own_buckets(mock_ctx: MagicMock) -> None:
    """Each shape type flushes through its own VAO/instance buffer."""
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    renderer.draw_circle(Vector2(50, 50), 10, Color(0, 255, 0))
    renderer.draw_line(Vector2(0, 0), Vector2(10, 0), Color(0, 0, 255))

    renderer.end_frame()

    circle_vao = renderer._shape_vaos[renderer.SHAPE_TYPE_CIRCLE]
    line_vao = renderer._shape_vaos[renderer.SHAPE_TYPE_LINE]
    rect_vao = renderer._shape_vaos[renderer.SHAPE_TYPE_RECT]

    assert circle_vao.render.call_args.kwargs["instances"] == 1
    assert line_vao.render.call_args.kwargs["instances"] == 1
    # Nothing was queued for rects this frame.
    rect_vao.render.assert_not_called()


def test_mixed_shapes_and_textures_do_not_interfere(mock_ctx: MagicMock) -> None:
    """draw_rect calls alongside render_batch() textured draws don't clobber
    each other's buffers -- the accepted no-Z-interleaving trade-off, not a
    correctness bug."""
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    mock_gl_tex = MagicMock()
    texture = GLTexture("test.png", mock_gl_tex, 32, 32)
    batch = RenderBatch(
        texture=texture,
        destinations=[(10, 10)],
        rotations=[],
        scales=[],
        transforms_enabled=False,
    )

    renderer.draw_rect(Rect(0, 0, 5, 5), Color(255, 255, 255))
    renderer.render_batch(batch)
    renderer.end_frame()

    sprite_vao = renderer._vao
    rect_vao = renderer._shape_vaos[renderer.SHAPE_TYPE_RECT]

    assert sprite_vao.render.call_args.kwargs["instances"] == 1
    assert rect_vao.render.call_args.kwargs["instances"] == 1


def test_draw_rect_grows_bucket_buffer_when_capacity_exceeded(
    mock_ctx: MagicMock,
) -> None:
    """A bucket's instance buffer grows independently, like the sprite path."""
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    original_capacity = renderer._shape_capacities[renderer.SHAPE_TYPE_RECT]

    for i in range(original_capacity + 1):
        renderer.draw_rect(Rect(i, 0, 1, 1), Color(0, 0, 0))

    renderer.end_frame()

    assert renderer._shape_capacities[renderer.SHAPE_TYPE_RECT] > original_capacity
    rect_vao = renderer._shape_vaos[renderer.SHAPE_TYPE_RECT]
    assert rect_vao.render.call_args.kwargs["instances"] == original_capacity + 1


# -- ModernGL world-space text (#71) --


def test_draw_text_uploads_a_texture_and_draws_it(mock_ctx: MagicMock) -> None:
    """draw_text() rasterizes via pygame.font, uploads the result as a GL
    texture, and draws it through the same single-instance path
    draw_texture() uses."""
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    renderer.draw_text("Hi", Vector2(10, 10), Color(255, 255, 255))

    mock_ctx.texture.assert_called_once()
    renderer._vao.render.assert_called()


def test_draw_text_keeps_the_texture_it_uploaded(mock_ctx: MagicMock) -> None:
    """The inverse of what this test used to assert, deliberately.

    It previously pinned "released immediately, because a fresh piece of
    text has nothing to reuse anyway". True of a string seen once, and
    wrong about what actually calls `draw_text`: `FloatingText` redraws the
    same damage numbers every frame for the life of the entry. The texture
    is now kept and reused, and `release()` owns freeing it.
    """
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    # `mock_ctx.texture`'s side_effect (see the `mock_ctx` fixture) returns a
    # fresh MagicMock per call, so `.return_value` is a distinct, unused mock
    # -- capture the one draw_text() actually gets back instead.
    created_gl_texture = MagicMock()
    mock_ctx.texture.side_effect = lambda *a, **k: created_gl_texture

    renderer.draw_text("Hi", Vector2(10, 10), Color(255, 255, 255))

    created_gl_texture.release.assert_not_called()


def test_drawing_the_same_string_again_uploads_nothing(mock_ctx: MagicMock) -> None:
    """The reason the cache exists: twenty live damage numbers cost twenty
    uploads and twenty frees *per frame*, for pixels identical to the
    previous frame's."""
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    for _ in range(5):
        renderer.draw_text("37", Vector2(10, 10), Color(255, 0, 0))

    assert mock_ctx.texture.call_count == 1


def test_text_that_looks_different_is_cached_separately(mock_ctx: MagicMock) -> None:
    """Everything that changes the pixels is in the key -- and nothing that
    does not, or the same glyphs drawn twice would upload twice."""
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    white, red = Color(255, 255, 255), Color(255, 0, 0)
    renderer.draw_text("A", Vector2(0, 0), white)
    renderer.draw_text("B", Vector2(0, 0), white)  # different string
    renderer.draw_text("A", Vector2(0, 0), red)  # different colour
    renderer.draw_text("A", Vector2(0, 0), white, size=32)  # different size

    assert mock_ctx.texture.call_count == 4

    renderer.draw_text("A", Vector2(99, 99), white)  # position is not pixels

    assert mock_ctx.texture.call_count == 4


def test_the_text_cache_is_bounded_and_releases_what_it_evicts(
    mock_ctx: MagicMock,
) -> None:
    """An FPS counter changes every frame, so the cache needs a ceiling --
    and reaching it has to free the GPU memory, which the garbage collector
    cannot do for a driver allocation."""
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    created: list[MagicMock] = []

    def fake_texture(*args: object, **kwargs: object) -> MagicMock:
        texture = MagicMock()
        created.append(texture)
        return texture

    mock_ctx.texture.side_effect = fake_texture

    overshoot = 10
    for n in range(_TEXT_CACHE_LIMIT + overshoot):
        renderer.draw_text(str(n), Vector2(0, 0), Color(255, 255, 255))

    assert len(renderer._text_cache) == _TEXT_CACHE_LIMIT
    assert sum(1 for texture in created if texture.release.called) == overshoot


def test_releasing_the_renderer_frees_the_cached_text(mock_ctx: MagicMock) -> None:
    """`draw_text` no longer frees what it draws, so this is the only thing
    that does."""
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    created_gl_texture = MagicMock()
    mock_ctx.texture.side_effect = lambda *a, **k: created_gl_texture
    renderer.draw_text("Hi", Vector2(10, 10), Color(255, 255, 255))

    renderer.release()

    created_gl_texture.release.assert_called_once()
    assert len(renderer._text_cache) == 0


def test_draw_text_empty_string_is_a_noop(mock_ctx: MagicMock) -> None:
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    renderer.draw_text("", Vector2(10, 10), Color(255, 255, 255))

    mock_ctx.texture.assert_not_called()


def test_draw_text_reuses_a_cached_font_for_the_same_size(mock_ctx: MagicMock) -> None:
    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    renderer.draw_text("a", Vector2(0, 0), Color(255, 255, 255), size=20)
    first_font = renderer._font_cache[20]

    renderer.draw_text("b", Vector2(0, 0), Color(255, 255, 255), size=20)

    assert renderer._font_cache[20] is first_font


def test_pygame_backend_draw_rect_untouched() -> None:
    """PygameBackend's own draw_rect/circle/line are a separate immediate-mode
    path and must not be affected by the ModernGL shape shader."""
    from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend

    assert "pygame.draw.rect" in inspect.getsource(PygameBackend.draw_rect)
    assert "pygame.draw.circle" in inspect.getsource(PygameBackend.draw_circle)
    assert "pygame.draw.line" in inspect.getsource(PygameBackend.draw_line)


def test_ui_renderer(mock_ctx: MagicMock) -> None:
    """UI Renderer should use pygame surface and upload texture.

    Asserts the *size* of what reaches the texture, not which pygame
    function produced it. It used to patch `pygame.image.tobytes` and
    assert the sentinel came back out, which pinned the mechanism rather
    than the behaviour: the renderer now hands GL the surface's own
    buffer and calls neither `tobytes` nor `transform.flip`, so the old
    assertion failed on a change that made the frame 3.3 ms cheaper and
    left every pixel identical. What matters here is that a whole
    surface's worth of pixels is uploaded and the dirty flag clears;
    `tests/integration/test_ui_renderer_pixels.py` checks that they are
    the *right* pixels, against real GL.
    """
    renderer = GLUIRenderer(mock_ctx, 800, 600)

    # Draw something
    renderer.draw_rect(Rect(0, 0, 10, 10), Color(255, 0, 0))
    assert renderer._dirty

    renderer.present()

    tex = renderer._texture
    assert isinstance(tex, MagicMock)
    tex.write.assert_called_once()
    (uploaded,) = tex.write.call_args.args
    assert uploaded.length == 800 * 600 * 4

    # Verify dirty flag was cleared
    assert not renderer._dirty


def test_gl_texture_release_is_idempotent() -> None:
    """`ResourceManager` releases on every eviction, and a backend teardown
    may reach the same texture, so a second call has to be harmless.

    It previously left `self._texture` in place and no flag, so the second
    call went through to moderngl on an already-released texture.
    """
    mock_gl_tex = MagicMock()
    texture = GLTexture("test.png", mock_gl_tex, 32, 32)

    texture.release()
    texture.release()
    texture.release()

    assert mock_gl_tex.release.call_count == 1


def test_gl_texture_reports_its_vram_so_the_budget_can_see_it() -> None:
    """The point of releasing on eviction: this is the memory the cache
    budget is counting, and the only thing that can free it."""
    texture = GLTexture("test.png", MagicMock(), 32, 32)

    assert texture.size_bytes > 0


def test_draw_text_uploads_its_glyphs_top_down(mock_ctx: MagicMock) -> None:
    """`draw_text` pre-flipped its surface to cancel a flip inside
    `GLTextureFactory.create_from_bytes`, so text came out the right way up
    via two wrongs. Both are gone, and this pins the result rather than the
    cancellation: what reaches `ctx.texture` must match pygame's own
    top-down byte order for the rendered surface.
    """
    import pygame

    with patch("builtins.open", mock_open(read_data="shader source")):
        renderer = ModernGLRenderer(mock_ctx, 800, 600)

    renderer.draw_text("Hi", Vector2(10, 10), Color(255, 255, 255))

    size, components, uploaded = mock_ctx.texture.call_args.args
    surface = renderer._get_font(16).render("Hi", True, (255, 255, 255, 255))

    assert size == surface.get_size()
    assert components == 4
    assert bytes(uploaded) == pygame.image.tobytes(surface, "RGBA", False)
