"""Integration tests for ModernGL graphics backend."""

import inspect
import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.config.types import WindowConfig
from pyguara.graphics.backends.moderngl.loaders import GLTextureLoader
from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer
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

    # Check if blending was enabled
    mock_ctx.enable.assert_called()


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

        with (
            patch("pygame.transform.flip", return_value=mock_surf),
            patch("pygame.image.tobytes", return_value=b"pixeldata"),
        ):
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


def test_pygame_backend_draw_rect_untouched() -> None:
    """PygameBackend's own draw_rect/circle/line are a separate immediate-mode
    path and must not be affected by the ModernGL shape shader."""
    from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend

    assert "pygame.draw.rect" in inspect.getsource(PygameBackend.draw_rect)
    assert "pygame.draw.circle" in inspect.getsource(PygameBackend.draw_circle)
    assert "pygame.draw.line" in inspect.getsource(PygameBackend.draw_line)


def test_ui_renderer(mock_ctx: MagicMock) -> None:
    """UI Renderer should use pygame surface and upload texture."""
    renderer = GLUIRenderer(mock_ctx, 800, 600)

    # Draw something
    renderer.draw_rect(Rect(0, 0, 10, 10), Color(255, 0, 0))
    assert renderer._dirty

    # Present (upload)
    with patch("pygame.image.tobytes", return_value=b"uidata"):
        renderer.present()

        # Check texture write
        tex = renderer._texture
        assert isinstance(tex, MagicMock)
        tex.write.assert_called_with(b"uidata")

        # Verify dirty flag was cleared
        assert not renderer._dirty
