"""A texture loaded from a file draws the way up it was drawn.

`GLTextureLoader` flipped every image it loaded "for OpenGL (origin at
bottom-left)". That is the right instinct for a quad whose UVs run
bottom-up, and `ModernGLRenderer`'s sprite quad does not: its top vertex
carries `v = 0` (`_create_quad_vbo`), so it wants the ordinary top-down
row order pygame already hands over. Every sprite loaded from a file
drew upside down.

No GL demo had noticed, because none of them loaded one -- they all
generate their textures at runtime through `GLTextureFactory`, which has
its own flip and its own callers pre-flipping to cancel it.

The context is mocked, so what these assert is the bytes handed to
`ctx.texture`: row 0 of the upload must be row 0 of the file.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pygame
import pytest

from pyguara.graphics.backends.moderngl.loaders import GLTextureLoader
from pyguara.graphics.backends.moderngl.texture import GLTextureFactory

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

WIDTH, HEIGHT = 4, 3
TOP = (255, 0, 0, 255)
BOTTOM = (0, 0, 255, 255)
MIDDLE = (0, 255, 0, 255)


@pytest.fixture(autouse=True)
def _display():
    """A display: `convert_alpha()` needs one, even under the dummy driver."""
    pygame.init()
    pygame.display.set_mode((1, 1))
    yield
    pygame.quit()


@pytest.fixture
def striped(tmp_path) -> str:
    """A 4x3 PNG whose three rows are red, green and blue, top to bottom."""
    surface = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
    for x in range(WIDTH):
        surface.set_at((x, 0), TOP)
        surface.set_at((x, 1), MIDDLE)
        surface.set_at((x, 2), BOTTOM)
    path = tmp_path / "striped.png"
    pygame.image.save(surface, str(path))
    return str(path)


@pytest.fixture
def ctx() -> MagicMock:
    mock = MagicMock()
    mock.texture.side_effect = lambda *args, **kwargs: MagicMock()
    return mock


def _rows(data: bytes) -> list[tuple[int, ...]]:
    """The uploaded bytes as one RGBA tuple per row (every row is flat)."""
    stride = WIDTH * 4
    return [tuple(data[i * stride : i * stride + 4]) for i in range(HEIGHT)]


def _uploaded(ctx: MagicMock) -> bytes:
    size, components, data = ctx.texture.call_args.args
    assert size == (WIDTH, HEIGHT)
    assert components == 4
    return bytes(data)


class TestOrientation:
    """Row 0 of the upload is row 0 of the file."""

    def test_the_first_row_uploaded_is_the_images_top_row(
        self, ctx: MagicMock, striped: str
    ) -> None:
        GLTextureLoader(ctx).load(striped)

        assert _rows(_uploaded(ctx))[0] == TOP

    def test_the_last_row_uploaded_is_the_images_bottom_row(
        self, ctx: MagicMock, striped: str
    ) -> None:
        GLTextureLoader(ctx).load(striped)

        assert _rows(_uploaded(ctx))[-1] == BOTTOM

    def test_the_whole_image_is_uploaded_top_down(
        self, ctx: MagicMock, striped: str
    ) -> None:
        GLTextureLoader(ctx).load(striped)

        assert _rows(_uploaded(ctx)) == [TOP, MIDDLE, BOTTOM]

    def test_the_sprite_quad_still_reads_v_zero_at_its_top(self) -> None:
        """What makes top-down the right order, read off the real quad.

        If `_create_quad_vbo` ever pairs the top of the sprite with
        `v = 1` instead, the loader has to flip again -- and this fails
        first.
        """
        from unittest.mock import mock_open, patch

        import numpy as np

        from pyguara.graphics.backends.moderngl.renderer import ModernGLRenderer

        ctx = MagicMock()
        ctx.buffer.side_effect = lambda *args, **kwargs: MagicMock()
        ctx.program.side_effect = lambda *args, **kwargs: MagicMock()
        ctx.vertex_array.side_effect = lambda *args, **kwargs: MagicMock()
        with patch("builtins.open", mock_open(read_data="shader source")):
            renderer = ModernGLRenderer(ctx, 800, 600)

        # The sprite quad is the first buffer the renderer builds.
        raw = ctx.buffer.call_args_list[0].args[0]
        vertices = np.frombuffer(raw, dtype="f4").reshape(-1, 4)
        assert renderer is not None

        # x, y, u, v. Screen space runs downward, so the quad's top
        # vertices are the ones with the smaller y.
        top = [row for row in vertices if row[1] < 0]
        bottom = [row for row in vertices if row[1] > 0]
        assert top and bottom
        assert all(row[3] == 0.0 for row in top), "the top of the quad samples v=0"
        assert all(row[3] == 1.0 for row in bottom)


class TestTheFactoryKeepsTheRowOrder:
    """`GLTextureFactory.create_from_bytes` used to reverse the rows.

    The reasoning in its docstring was that OpenGL's origin is bottom-left.
    True of GL in general, not of this renderer -- see the module docstring
    above. So the factory disagreed with the loader beside it, and whether
    an upload came out the right way up depended on which of the two it
    went through.
    """

    def _top_down(self) -> bytes:
        """The striped image as raw bytes, top row first.

        What both producers in this tree hand over: pygame's
        `image.tobytes(..., False)` and PIL's `tobytes("raw", "RGBA")`.
        """
        return b"".join(bytes(colour) * WIDTH for colour in (TOP, MIDDLE, BOTTOM))

    def test_the_first_row_uploaded_is_the_first_row_given(
        self, ctx: MagicMock
    ) -> None:
        GLTextureFactory(ctx).create_from_bytes(
            "probe", self._top_down(), WIDTH, HEIGHT
        )

        assert _rows(_uploaded(ctx))[0] == TOP

    def test_the_last_row_uploaded_is_the_last_row_given(self, ctx: MagicMock) -> None:
        GLTextureFactory(ctx).create_from_bytes(
            "probe", self._top_down(), WIDTH, HEIGHT
        )

        assert _rows(_uploaded(ctx))[-1] == BOTTOM

    def test_the_factory_and_the_loader_agree(
        self, ctx: MagicMock, striped: str
    ) -> None:
        """The actual defect: two upload paths, two conventions. Whichever
        way round the convention goes, these two must match."""
        GLTextureLoader(ctx).load(striped)
        via_loader = _uploaded(ctx)

        ctx.texture.reset_mock()
        GLTextureFactory(ctx).create_from_bytes(
            "probe", self._top_down(), WIDTH, HEIGHT
        )
        via_factory = _uploaded(ctx)

        assert _rows(via_factory) == _rows(via_loader)


class TestSpriteSheetUploadsTheRightWayUp:
    """Every sliced frame was upside down on the GL backend.

    `SpriteSheet` hands the factory PIL's `tobytes("raw", "RGBA")`, which is
    top-down, and the factory reversed it. Latent only because no GL demo
    loads a sheet -- they all generate their textures at runtime, through
    paths that are vertically symmetric or that pre-flipped to cancel it.
    """

    def test_a_sliced_frame_keeps_its_top_row_on_top(self, ctx: MagicMock) -> None:
        from PIL import Image

        from pyguara.graphics.spritesheet import SpriteSheet

        # One frame, three stripes, same as the file fixture.
        image = Image.new("RGBA", (WIDTH, HEIGHT))
        for x in range(WIDTH):
            image.putpixel((x, 0), TOP)
            image.putpixel((x, 1), MIDDLE)
            image.putpixel((x, 2), BOTTOM)

        sheet = SpriteSheet.from_image(image, GLTextureFactory(ctx), "sheet.png")
        sheet.slice_grid(WIDTH, HEIGHT)

        assert _rows(_uploaded(ctx))[0] == TOP
