"""A character the default face lacks is drawn from a fallback face.

`tests/fixtures/fonts/PyguaraTestCJK.ttf` has 一, あ, 가 and 。 -- none of
which Liberation Sans has -- and an `A` shaped as a solid block, which must
not be used, because Liberation has its own.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from pyguara.graphics import fonts

try:
    from pyguara import pyguara_core_rs as extension
except ImportError:  # pragma: no cover - the wheel always ships it
    extension = None

needs_extension = pytest.mark.skipif(extension is None, reason="extension not built")

CJK = Path(__file__).parent / "fixtures" / "fonts" / "PyguaraTestCJK.ttf"


@pytest.fixture(autouse=True)
def _no_fallbacks_after():
    yield
    fonts.set_fallback_fonts([])


# --------------------------------------------------------------------------- #
# The registry                                                                 #
# --------------------------------------------------------------------------- #


def test_there_are_none_by_default() -> None:
    assert fonts.fallback_fonts() == ()


def test_setting_them_bumps_the_generation() -> None:
    before = fonts.fallback_generation()
    fonts.set_fallback_fonts([CJK])
    assert fonts.fallback_fonts() == (CJK,)
    assert fonts.fallback_generation() == before + 1


def test_a_missing_file_is_refused_by_name(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="nope.otf"):
        fonts.set_fallback_fonts([tmp_path / "nope.otf"])
    assert fonts.fallback_fonts() == ()


@needs_extension
def test_a_file_that_is_not_a_font_is_refused(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.ttf"
    bogus.write_bytes(b"not a font")
    with pytest.raises(OSError, match="bogus.ttf"):
        fonts.set_fallback_fonts([bogus])


@needs_extension
def test_each_character_is_given_the_first_face_that_has_it() -> None:
    assert fonts.faces_for("A一.") == [0, 0, 0]  # nothing to fall back to
    fonts.set_fallback_fonts([CJK])
    assert fonts.faces_for("A一あ가。z") == [0, 1, 1, 1, 1, 0]
    assert fonts.faces_for("\U0001f600") == [0], "no face has it: the default's box"


# --------------------------------------------------------------------------- #
# wgpu: NativeFont                                                             #
# --------------------------------------------------------------------------- #


@needs_extension
def test_the_native_font_draws_the_fallback_glyph() -> None:
    font = extension.NativeFont(32)
    without = font.render("一")
    font.set_fallbacks([extension.NativeFace(CJK.read_bytes())])
    with_fallback = font.render("一")

    assert font.faces_used("A一") == [0, 1]
    assert with_fallback[0] != without[0], "the .notdef box was drawn, not 一"
    # 一 in the test face is one bar, 900 units wide at 32 px: ~29 px.
    assert 27 <= with_fallback[1] <= 32


@needs_extension
def test_line_metrics_stay_the_default_faces() -> None:
    plain = extension.NativeFont(24)
    mixed = extension.NativeFont(24)
    mixed.set_fallbacks([extension.NativeFace(CJK.read_bytes())])
    assert mixed.height == plain.height
    assert mixed.ascent == plain.ascent
    assert mixed.size("A一")[1] == plain.size("A")[1]


@needs_extension
def test_latin_text_is_unchanged_by_a_fallback() -> None:
    plain = extension.NativeFont(20)
    mixed = extension.NativeFont(20)
    mixed.set_fallbacks([extension.NativeFace(CJK.read_bytes())])
    assert mixed.render("AVATAR Wave") == plain.render("AVATAR Wave")


@needs_extension
def test_the_frame_rebuilds_its_fonts_when_the_fallbacks_change() -> None:
    from pyguara.graphics.backends.wgpu.frame import GpuFrame

    try:
        frame = GpuFrame(64, 64, None)
    except RuntimeError as error:
        if os.environ.get("PYGUARA_REQUIRE_GPU"):
            raise
        pytest.skip(f"no graphics adapter: {error}")
    before = frame.font(20).size("一")
    fonts.set_fallback_fonts([CJK])
    after = frame.font(20).size("一")
    assert after != before


# --------------------------------------------------------------------------- #
# pygame                                                                       #
# --------------------------------------------------------------------------- #


@pytest.fixture
def pygame_ui():
    pygame.init()
    from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer

    surface = pygame.Surface((200, 60), pygame.SRCALPHA)
    yield PygameUIRenderer(surface)
    pygame.quit()


def _ink(surface: pygame.Surface) -> int:
    return sum(
        1
        for x in range(surface.get_width())
        for y in range(surface.get_height())
        if surface.get_at((x, y)).a > 0
    )


@needs_extension
def test_pygame_draws_the_fallback_glyph_and_measures_it(pygame_ui) -> None:
    from pyguara.common.types import Color, Vector2

    def drawn(text: str) -> pygame.Surface:
        pygame_ui._surface.fill((0, 0, 0, 0))
        pygame_ui.draw_text(text, Vector2(0, 0), Color(255, 255, 255), 32)
        return pygame_ui._surface.copy()

    box = pygame.image.tobytes(drawn("一"), "RGBA")
    width_before = pygame_ui.get_text_size("A一", 32)[0]

    fonts.set_fallback_fonts([CJK])

    bar = drawn("一")
    assert pygame.image.tobytes(bar, "RGBA") != box
    # One bar: ink in a band, none above or below it.
    rows = {y for x in range(200) for y in range(60) if bar.get_at((x, y)).a > 128}
    assert rows and max(rows) - min(rows) <= 5
    width_after = pygame_ui.get_text_size("A一", 32)[0]
    assert width_after != width_before
    assert pygame_ui.get_text_size("A一", 32)[1] == pygame_ui.get_text_size("A", 32)[1]


def test_pygame_latin_text_is_unchanged_by_a_fallback(pygame_ui) -> None:
    from pyguara.common.types import Color, Vector2

    pygame_ui.draw_text("AVATAR Wave", Vector2(0, 0), Color(255, 255, 255), 20)
    plain = pygame.image.tobytes(pygame_ui._surface, "RGBA")
    pygame_ui._surface.fill((0, 0, 0, 0))
    fonts.set_fallback_fonts([CJK])
    pygame_ui.draw_text("AVATAR Wave", Vector2(0, 0), Color(255, 255, 255), 20)
    assert pygame.image.tobytes(pygame_ui._surface, "RGBA") == plain
