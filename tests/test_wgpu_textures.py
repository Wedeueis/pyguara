"""The wgpu backend's images: decoded in Rust, uploaded once, never via pygame.

The decoder is held to `pygame.image.load` on every PNG this repository
ships, byte for byte. pygame is imported here only as that reference.
"""

from __future__ import annotations

import gc
import logging
from pathlib import Path
from typing import Any

import pytest

from pyguara import native
from pyguara.graphics.backends.wgpu.textures import (
    ImageTexture,
    ImageTextureFactory,
    NativeImageLoader,
)
from pyguara.resources.meta import TextureMeta

try:
    extension: Any = native.require_extension("tests")
except RuntimeError:
    extension = None

pytestmark = pytest.mark.skipif(extension is None, reason="extension not built")

ROOT = Path(__file__).resolve().parent.parent
PNGS = sorted(
    path
    for folder in ("games", "assets")
    for path in (ROOT / folder).rglob("*.png")
    if ".agent-view" not in path.parts
)
JPEGS = sorted((ROOT / "assets").rglob("*.jpg"))


def _pygame_rgba(path: Path) -> tuple[bytes, int, int]:
    import pygame

    surface = pygame.image.load(str(path))
    with_alpha = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    with_alpha.blit(surface, (0, 0))
    width, height = with_alpha.get_size()
    return pygame.image.tobytes(with_alpha, "RGBA"), width, height


class TestDecode:
    @pytest.mark.parametrize("path", PNGS, ids=lambda p: str(p.relative_to(ROOT)))
    def test_every_shipped_png_decodes_as_pygame_decodes_it(self, path: Path) -> None:
        pixels, width, height = extension.decode_image(str(path))
        expected, expected_width, expected_height = _pygame_rgba(path)

        assert (width, height) == (expected_width, expected_height)
        assert bytes(pixels) == expected

    @pytest.mark.parametrize("path", JPEGS, ids=lambda p: p.name)
    def test_a_jpeg_decodes_within_rounding_of_pygame(self, path: Path) -> None:
        """Two JPEG decoders round the colour transform differently.

        Measured on these three: at most 4/255 on a channel, a mean under
        0.13. Held to 4 and 0.5, which a wrong colour space or a dropped
        chroma plane exceeds by an order of magnitude.
        """
        import numpy as np

        pixels, width, height = extension.decode_image(str(path))
        expected, expected_width, expected_height = _pygame_rgba(path)

        assert (width, height) == (expected_width, expected_height)
        ours = np.frombuffer(bytes(pixels), np.uint8).astype(np.int16)
        theirs = np.frombuffer(expected, np.uint8).astype(np.int16)
        difference = np.abs(ours - theirs)
        assert difference.max() <= 4
        assert difference.mean() < 0.5

    def test_a_file_that_is_not_an_image_is_an_os_error(self, tmp_path: Path) -> None:
        path = tmp_path / "broken.png"
        path.write_bytes(b"not a png")
        with pytest.raises(OSError, match="broken.png"):
            extension.decode_image(str(path))

    def test_a_missing_file_is_an_os_error(self, tmp_path: Path) -> None:
        with pytest.raises(OSError):
            extension.decode_image(str(tmp_path / "nowhere.png"))


class TestEncode:
    def test_a_png_round_trips(self, tmp_path: Path) -> None:
        pixels = bytes(range(256)) * 3  # 3 rows of 64 RGBA pixels
        path = tmp_path / "out.png"

        extension.encode_png(str(path), pixels, 64, 3)

        assert extension.decode_image(str(path)) == (pixels, 64, 3)

    def test_the_byte_count_must_match_the_size(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="2x2"):
            extension.encode_png(str(tmp_path / "x.png"), b"\0" * 12, 2, 2)


class TestPremultiply:
    def test_colour_is_scaled_by_alpha_rounding_down(self) -> None:
        out = extension.premultiply_rgba(bytes([255, 128, 10, 128, 200, 200, 200, 0]))
        assert bytes(out) == bytes([128, 64, 5, 128, 0, 0, 0, 0])

    def test_opaque_pixels_are_unchanged(self) -> None:
        pixels = bytes([12, 34, 56, 255])
        assert bytes(extension.premultiply_rgba(pixels)) == pixels

    def test_a_partial_pixel_is_refused(self) -> None:
        with pytest.raises(ValueError, match="RGBA"):
            extension.premultiply_rgba(b"\0\0\0")


def _write_png(tmp_path: Path, pixels: bytes, width: int, height: int) -> str:
    path = tmp_path / "image.png"
    extension.encode_png(str(path), pixels, width, height)
    return str(path)


class TestLoader:
    def test_it_loads_an_image_texture(self, tmp_path: Path) -> None:
        path = _write_png(tmp_path, bytes([1, 2, 3, 4]) * 6, 3, 2)

        texture = NativeImageLoader().load(path)

        assert isinstance(texture, ImageTexture)
        assert (texture.width, texture.height) == (3, 2)
        assert texture.pixels == bytes([1, 2, 3, 4]) * 6
        assert texture.smooth is False

    def test_the_meta_filter_and_premultiply_apply(self, tmp_path: Path) -> None:
        path = _write_png(tmp_path, bytes([200, 100, 50, 128]), 1, 1)
        meta = TextureMeta(filter="linear", premultiply_alpha=True)

        texture = NativeImageLoader().load_with_meta(path, meta)

        assert texture.smooth is True  # type: ignore[attr-defined]
        assert texture.pixels == bytes([100, 50, 25, 128])  # type: ignore[attr-defined]


class TestImageTexture:
    def test_the_byte_count_must_match_the_size(self) -> None:
        with pytest.raises(ValueError, match="2x2"):
            ImageTexture("t", b"\0" * 4, 2, 2)

    def test_the_factory_copies_the_bytes(self) -> None:
        data = bytearray(b"\x01\x02\x03\x04")
        texture = ImageTextureFactory().create_from_bytes("t", data, 1, 1)
        data[0] = 99
        assert texture.pixels == b"\x01\x02\x03\x04"  # type: ignore[attr-defined]
        assert texture.size_bytes == 4


@pytest.fixture
def frame() -> Any:
    from pyguara.graphics.backends.wgpu import GpuFrame

    try:
        return GpuFrame(8, 8)
    except RuntimeError as error:
        pytest.skip(f"no graphics adapter for wgpu: {error}")


class TestUpload:
    def test_an_image_is_uploaded_once_per_filter(self, frame: Any) -> None:
        texture = ImageTexture("t", b"\xff" * 16, 2, 2)
        before = frame.gpu.texture_count

        first = frame.image(texture)
        assert frame.image(texture) == first
        assert first[1:] == (2, 2)
        assert frame.image(texture, smooth=True) != first
        assert frame.gpu.texture_count == before + 2

    def test_a_collected_image_frees_its_texture_after_the_frame(
        self, frame: Any
    ) -> None:
        texture = ImageTexture("t", b"\xff" * 4, 1, 1)
        frame.image(texture)
        counted = frame.gpu.texture_count

        del texture
        gc.collect()
        frame.gpu.end_frame()
        frame.after_frame()

        assert frame.gpu.texture_count == counted - 1

    def test_something_that_is_not_an_image_draws_nothing_and_says_so_once(
        self, frame: Any, caplog: pytest.LogCaptureFixture
    ) -> None:
        class NotAnImage: ...

        with caplog.at_level(logging.WARNING):
            assert frame.image(NotAnImage()) is None
            assert frame.image(NotAnImage()) is None

        assert sum("NotAnImage" in r.getMessage() for r in caplog.records) == 1
