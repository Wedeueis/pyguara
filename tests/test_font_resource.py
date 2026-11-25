"""A game's own font loads through `ResourceManager` and draws on every renderer.

The font used is the engine's own bold face, loaded as a game would load
any `.ttf`: drawn as a `Font`, it must come out exactly as the default
face drawn with `bold=True`, which proves the renderer used the file and
not its built-in face.
"""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from pyguara.common.types import Color, Vector2
from pyguara.graphics import fonts
from pyguara.graphics.backends.headless_renderer import HeadlessUIRenderer
from pyguara.graphics.backends.pygame.fallback_font import FallbackFont
from pyguara.graphics.backends.pygame.pygame_renderer import PygameBackend
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.resources import BlobLoader, Font, FontLoader, ResourceManager

CJK = Path(__file__).parent / "fixtures" / "fonts" / "PyguaraTestCJK.ttf"
BOLD = fonts.default_font_path(bold=True)
WHITE = Color(255, 255, 255)


@pytest.fixture(autouse=True)
def _no_fallbacks_after():
    yield
    fonts.set_fallback_fonts([])


@pytest.fixture
def bold() -> Font:
    manager = ResourceManager()
    manager.register_loader(FontLoader())
    return manager.load(str(BOLD), Font)


def _frame():
    from pyguara.graphics.backends.wgpu.frame import GpuFrame

    try:
        return GpuFrame(64, 64, None)
    except RuntimeError as error:
        if os.environ.get("PYGUARA_REQUIRE_GPU"):
            raise
        pytest.skip(f"no graphics adapter: {error}")


# --------------------------------------------------------------------------- #
# The resource                                                                 #
# --------------------------------------------------------------------------- #


def test_a_font_file_loads_as_a_font(bold: Font) -> None:
    assert bold.path == str(BOLD)
    assert bold.data == BOLD.read_bytes()
    assert bold.size_bytes == len(bold.data)
    assert bold.native_handle is bold


def test_a_file_that_is_not_a_font_is_refused_by_name(tmp_path: Path) -> None:
    bogus = tmp_path / "bogus.ttf"
    bogus.write_bytes(b"not a font")
    with pytest.raises(OSError, match="bogus.ttf"):
        FontLoader().load(str(bogus))


def test_the_blob_loader_no_longer_claims_fonts() -> None:
    assert not {".ttf", ".otf"} & set(BlobLoader().supported_extensions)


def test_the_application_loads_fonts() -> None:
    from pyguara.application.bootstrap import create_headless_application

    application = create_headless_application()
    resources = application.container.get(ResourceManager)
    assert isinstance(resources.load(str(BOLD), Font), Font)


# --------------------------------------------------------------------------- #
# pygame                                                                       #
# --------------------------------------------------------------------------- #


def _pixels(surface: pygame.Surface) -> bytes:
    return pygame.image.tobytes(surface, "RGBA")


def test_the_pygame_ui_draws_and_measures_in_the_font(bold: Font) -> None:
    by_style = PygameUIRenderer(pygame.Surface((200, 40), pygame.SRCALPHA))
    by_font = PygameUIRenderer(pygame.Surface((200, 40), pygame.SRCALPHA))

    by_style.draw_text("Wave 12", Vector2(2, 2), WHITE, 20, bold=True)
    by_font.draw_text("Wave 12", Vector2(2, 2), WHITE, 20, font=bold)

    assert _pixels(by_font._surface) == _pixels(by_style._surface)
    assert by_font.get_text_size("Wave 12", 20, font=bold) == (
        by_style.get_text_size("Wave 12", 20, bold=True)
    )
    assert by_font.get_text_size("Wave 12", 20, font=bold) != (
        by_font.get_text_size("Wave 12", 20)
    )
    assert by_font.get_line_height(20, font=bold) == by_font.get_line_height(20)


def test_the_pygame_world_renderer_draws_in_the_font(bold: Font) -> None:
    pygame.display.init()
    pygame.display.set_mode((200, 40))
    world = PygameBackend(pygame.Surface((200, 40), pygame.SRCALPHA))
    ui = PygameUIRenderer(pygame.Surface((200, 40), pygame.SRCALPHA))

    world.draw_text("Wave 12", Vector2(2, 2), WHITE, 20, font=bold)
    ui.draw_text("Wave 12", Vector2(2, 2), WHITE, 20, bold=True)

    assert _pixels(world._screen) == _pixels(ui._surface)


def test_a_fonts_missing_characters_come_from_the_fallbacks(bold: Font) -> None:
    fonts.set_fallback_fonts([CJK])
    face = FallbackFont(20, face=bold)
    runs = face.runs("A一")
    assert [text for _, text in runs] == ["A", "一"]
    assert runs[0][0] is face.primary


# --------------------------------------------------------------------------- #
# wgpu                                                                         #
# --------------------------------------------------------------------------- #


def test_the_wgpu_frame_draws_and_measures_in_the_font(bold: Font) -> None:
    frame = _frame()
    by_font = frame.font(20, face=bold)
    by_style = frame.font(20, bold=True)

    assert by_font is frame.font(20, face=bold), "made once per size and face"
    assert by_font is not by_style
    assert by_font.render("Wave 12") == by_style.render("Wave 12")
    assert by_font.size("Wave 12") != frame.font(20).size("Wave 12")


def test_the_wgpu_frame_gives_a_font_the_fallbacks(bold: Font) -> None:
    frame = _frame()
    fonts.set_fallback_fonts([CJK])
    assert frame.font(20, face=bold).faces_used("A一") == [0, 1]


# --------------------------------------------------------------------------- #
# A style asked of a font                                                      #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("style", [{"bold": True}, {"italic": True}])
def test_a_style_asked_of_a_font_is_refused(bold: Font, style: dict) -> None:
    pygame_ui = PygameUIRenderer(pygame.Surface((10, 10)))
    for measure in (pygame_ui.get_text_size, HeadlessUIRenderer().get_text_size):
        with pytest.raises(ValueError, match="one face"):
            measure("x", 16, font=bold, **style)
    with pytest.raises(ValueError, match="one face"):
        HeadlessUIRenderer().draw_text("x", Vector2(0, 0), WHITE, font=bold, **style)


def test_a_style_asked_of_a_font_is_refused_on_wgpu(bold: Font) -> None:
    with pytest.raises(ValueError, match="one face"):
        _frame().font(16, bold=True, face=bold)
