"""Integration tests for ModernGL graphics backend."""

import os
import pytest
from unittest.mock import MagicMock, patch, mock_open

# ... imports ...
from pyguara.graphics.backends.moderngl.window import PygameGLWindow
from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer
from pyguara.graphics.backends.moderngl.texture import GLTexture
from pyguara.graphics.backends.moderngl.loaders import GLTextureLoader
from pyguara.graphics.backends.moderngl.ui_renderer import GLUIRenderer
from pyguara.config.types import WindowConfig
from pyguara.common.types import Color, Rect
from pyguara.graphics.types import RenderBatch

# Ensure headless execution for pygame parts
os.environ["SDL_VIDEODRIVER"] = "dummy"


@pytest.fixture
def mock_ctx() -> MagicMock:
    """Create a mock ModernGL context."""
    ctx = MagicMock()
    ctx.buffer.return_value = MagicMock()
    ctx.program.return_value = MagicMock()
    ctx.vertex_array.return_value = MagicMock()
    ctx.texture.return_value = MagicMock()
    return ctx


@pytest.fixture
def gl_window(mock_ctx: MagicMock) -> PygameGLWindow:
    """Create a PygameGLWindow with a mocked context."""
    with patch("moderngl.create_context", return_value=mock_ctx):
        with patch("pygame.display.set_mode"):
            with patch("pygame.display.gl_set_attribute"):
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

    mock_ctx.program.assert_called_once()

    assert mock_ctx.buffer.call_count >= 2  # Quad VBO + Instance VBO
    mock_ctx.vertex_array.assert_called_once()


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

        with patch("pygame.transform.flip", return_value=mock_surf):
            with patch("pygame.image.tobytes", return_value=b"pixeldata"):
                texture = loader.load("test.png")

                assert isinstance(texture, GLTexture)
                assert texture.width == 100
                mock_ctx.texture.assert_called_with((100, 100), 4, b"pixeldata")


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
