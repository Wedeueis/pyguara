"""A theme's fonts are what every widget draws in, and survive a save and load.

The engine's own bold face, loaded as a game font, stands in for a game's:
a widget drawn in it must measure as the default face's bold does.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import pytest

from pyguara.common.types import Vector2
from pyguara.graphics import fonts
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.resources import Font, FontLoader, ResourceManager
from pyguara.ui.components.button import Button
from pyguara.ui.components.rich_label import RichLabel
from pyguara.ui.components.text import Label
from pyguara.ui.theme import ThemeValidationError, UITheme, get_theme, set_theme
from pyguara.ui.types import FontScheme, text_style

BOLD = fonts.default_font_path(bold=True)
ITALIC = fonts.default_font_path(italic=True)


@pytest.fixture
def resources() -> ResourceManager:
    manager = ResourceManager()
    manager.register_loader(FontLoader())
    return manager


@pytest.fixture
def heavy(resources: ResourceManager) -> Font:
    return resources.load(str(BOLD), Font)


@pytest.fixture
def themed(heavy: Font):
    """Make `heavy` the regular face of the active theme, then put it back."""
    before = get_theme()
    theme = before.clone()
    theme.fonts.regular = heavy
    set_theme(theme)
    yield theme
    set_theme(before)


class _Recorder:
    """A UI renderer that measures every string as 10 px a character."""

    def __init__(self) -> None:
        self.drawn: list[dict[str, Any]] = []
        self.measured: list[dict[str, Any]] = []

    def get_text_size(self, text: str, size: int, **style: Any) -> tuple[int, int]:
        self.measured.append(style)
        return (10 * len(text), size)

    def get_line_height(self, size: int, **style: Any) -> int:
        return size + 2

    def draw_text(
        self, text: str, position: Any, color: Any, size: int = 16, **style: Any
    ) -> None:
        self.drawn.append({"text": text, "size": size, **style})

    def __getattr__(self, name: str) -> Any:
        return lambda *args, **kwargs: None


# --------------------------------------------------------------------------- #
# Choosing a face                                                              #
# --------------------------------------------------------------------------- #


def test_without_faces_a_style_is_the_default_faces(heavy: Font) -> None:
    assert text_style(FontScheme(), bold=True) == {"bold": True}
    assert text_style(FontScheme()) == {}


def test_a_style_with_a_face_is_drawn_in_it(heavy: Font) -> None:
    scheme = FontScheme(regular=heavy, bold=heavy)
    assert text_style(scheme) == {"font": heavy}
    assert text_style(scheme, bold=True)["font"] is heavy


def test_a_style_whose_face_is_missing_is_refused(heavy: Font) -> None:
    with pytest.raises(ValueError, match="no bold_italic face"):
        text_style(FontScheme(regular=heavy), bold=True, italic=True)


# --------------------------------------------------------------------------- #
# Widgets                                                                      #
# --------------------------------------------------------------------------- #


def test_a_label_draws_and_measures_in_the_themes_font(themed: UITheme) -> None:
    renderer = _Recorder()
    label = Label("Wave 12", Vector2(0, 0), 20)
    label.render(renderer)

    assert renderer.drawn == [
        {"text": "Wave 12", "size": 20, "font": themed.fonts.regular}
    ]
    assert all(style.get("font") is themed.fonts.regular for style in renderer.measured)


def test_a_label_is_sized_by_the_themes_font(themed: UITheme) -> None:
    renderer = PygameUIRenderer(pygame.Surface((200, 40), pygame.SRCALPHA))
    label = Label("Wave 12", Vector2(0, 0), 20)
    label.measure(renderer)
    assert (label.rect.width, label.rect.height) == renderer.get_text_size(
        "Wave 12", 20, bold=True
    )


def test_a_button_draws_its_text_at_the_size_it_measured(themed: UITheme) -> None:
    themed.fonts.size_normal = 22
    renderer = _Recorder()
    Button("Play", Vector2(0, 0), Vector2(100, 40)).render(renderer)
    assert [(draw["size"], draw.get("font")) for draw in renderer.drawn] == [
        (22, themed.fonts.regular)
    ]


def test_rich_text_takes_each_style_from_its_face(
    themed: UITheme, resources: ResourceManager
) -> None:
    slanted = resources.load(str(ITALIC), Font)
    themed.fonts.italic = slanted
    renderer = _Recorder()
    RichLabel("plain [i]leaning[/i]").render(renderer)
    assert [(draw["text"], draw.get("font")) for draw in renderer.drawn] == [
        ("plain ", themed.fonts.regular),
        ("leaning", slanted),
    ]


def test_rich_text_in_a_style_the_theme_lacks_is_refused(themed: UITheme) -> None:
    with pytest.raises(ValueError, match="no bold face"):
        RichLabel("a [b]bold[/b] claim").render(_Recorder())


# --------------------------------------------------------------------------- #
# Saving and loading                                                           #
# --------------------------------------------------------------------------- #


def test_a_theme_saves_its_faces_as_paths_and_loads_them_back(
    heavy: Font, resources: ResourceManager, tmp_path: Path
) -> None:
    theme = UITheme(fonts=FontScheme(regular=heavy))
    path = tmp_path / "theme.json"
    theme.save(path)

    assert '"regular": "' in path.read_text()
    loaded = UITheme.load(path, resources)
    assert loaded.fonts.regular is heavy, "loaded through the same cache"
    assert loaded.fonts.bold is None


def test_a_theme_naming_a_font_needs_resources_to_load(
    heavy: Font, tmp_path: Path
) -> None:
    path = tmp_path / "theme.json"
    UITheme(fonts=FontScheme(regular=heavy)).save(path)
    with pytest.raises(ThemeValidationError, match="pass resources="):
        UITheme.load(path)


def test_a_face_that_is_not_a_path_is_refused() -> None:
    with pytest.raises(ThemeValidationError, match="fonts.bold"):
        UITheme.from_dict({"fonts": {"bold": 12}})


def test_a_clone_shares_the_faces(heavy: Font) -> None:
    theme = UITheme(fonts=FontScheme(regular=heavy))
    assert theme.clone().fonts.regular is heavy
