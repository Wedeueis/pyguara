"""`NativeFont`: the wgpu backend's text, without a renderer around it.

How it measures against `pygame.font` is `test_wgpu_pixels.TestTextMetrics`;
this is its own contract.
"""

from __future__ import annotations

from typing import Any

import pytest

from pyguara import native
from pyguara.graphics.fonts import default_font_path

try:
    extension: Any = native.require_extension("tests")
except RuntimeError:
    extension = None

pytestmark = pytest.mark.skipif(extension is None, reason="extension not built")


def test_a_string_renders_white_with_its_coverage_as_alpha() -> None:
    pixels, width, height = extension.NativeFont(20).render("Hi")

    assert len(pixels) == width * height * 4
    assert width > 0 and height == extension.NativeFont(20).height
    assert set(pixels[0::4]) == {255}
    assert max(pixels[3::4]) == 255
    assert (width, height) == extension.NativeFont(20).size("Hi")


def test_an_empty_string_has_a_height_and_no_pixels() -> None:
    font = extension.NativeFont(16)
    assert font.render("") == (b"", 0, font.height)
    assert font.size("") == (0, font.height)


def test_a_space_has_width_and_no_ink() -> None:
    pixels, width, _ = extension.NativeFont(16).render("  ")
    assert width > 0
    assert max(pixels[3::4]) == 0


def test_the_styles_are_different_faces() -> None:
    renders = {
        extension.NativeFont(24, bold, italic).render("Wave")[0]
        for bold in (False, True)
        for italic in (False, True)
    }
    assert len(renders) == 4


def test_a_font_file_loads_and_matches_the_embedded_face() -> None:
    data = default_font_path(bold=True).read_bytes()
    loaded = extension.NativeFont.from_bytes(data, 18)
    assert loaded.render("Iron Lung") == extension.NativeFont(18, True).render(
        "Iron Lung"
    )


def test_bytes_that_are_not_a_font_are_an_os_error() -> None:
    with pytest.raises(OSError, match="not a font"):
        extension.NativeFont.from_bytes(b"definitely not a font", 12)


def test_a_zero_size_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        extension.NativeFont(0)


def test_the_bundled_files_are_the_ones_shipped_beside_their_licence() -> None:
    for bold in (False, True):
        for italic in (False, True):
            assert default_font_path(bold, italic).is_file()
    assert (default_font_path().parent / "OFL.txt").is_file()
