"""The design system: tokens, the Cerrado themes, the bevel, the two widgets.

The integration this covers is the point of the module. A design system
that shipped its own `Surface`-drawing widget tree would be untestable
without a display, would not render on the ModernGL backend at all, and
would drift from the components the engine already maintains. Everything
here goes through `UIRenderer`, so a `MagicMock` is enough to assert what
reaches the backend.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.design_system import (
    BevelButton,
    BevelPanel,
    Skins,
    bevel_edges,
    cerrado_day,
    cerrado_dusk,
    draw_bevel,
    draw_stamp_shadow,
    tokens,
)
from pyguara.ui.theme import get_theme, set_theme
from pyguara.ui.types import UIElementState


@pytest.fixture
def renderer() -> Any:
    r = MagicMock(spec=UIRenderer)
    r.get_text_size.return_value = (40, 16)
    return r


@pytest.fixture
def dusk() -> Any:
    """Run the test under the dusk theme, then restore."""
    previous = get_theme()
    set_theme(cerrado_dusk())
    yield
    set_theme(previous)


class TestTokens:
    def test_a_token_is_the_hex_it_documents(self) -> None:
        assert tokens.Guara.C500.to_hex() == "#E2621F"
        assert tokens.Roxo.C900.to_hex() == "#241531"

    def test_tokens_are_opaque(self) -> None:
        """A palette entry with stray alpha would silently wash out."""
        families = (tokens.Guara, tokens.Sand, tokens.Wood, tokens.Verdant)
        colors = [
            value
            for family in families
            for name, value in vars(family).items()
            if isinstance(value, Color)
        ]

        assert colors
        assert all(color.a == 255 for color in colors)


class TestTheCerradoThemes:
    @pytest.mark.parametrize(
        "factory", [cerrado_dusk, cerrado_day], ids=["dusk", "day"]
    )
    def test_every_role_is_populated(self, factory: Any) -> None:
        colors = factory().colors

        assert colors.surface_card is not None
        assert colors.action_primary_press is not None
        assert colors.text_on_primary is not None

    def test_each_call_returns_a_fresh_theme(self) -> None:
        """A preset handed out by reference gets mutated by its first user."""
        first = cerrado_dusk()
        first.colors.action_primary = Color(1, 2, 3)

        assert cerrado_dusk().colors.action_primary != Color(1, 2, 3)

    def test_dusk_is_dark_and_day_is_light(self) -> None:
        assert cerrado_dusk().colors.surface_canvas.r < 60
        assert cerrado_day().colors.surface_canvas.r > 200

    def test_the_action_colour_is_the_brand_orange(self) -> None:
        assert cerrado_dusk().colors.action_primary == tokens.Guara.C500
        assert cerrado_day().colors.action_primary == tokens.Guara.C600

    def test_setting_the_theme_reskins_a_stock_component(self, dusk: None) -> None:
        """The whole reason the themes are `UITheme`s and not a private type."""
        from pyguara.ui.components.button import Button

        button = Button("Play", Vector2(0, 0))

        assert button.fill_color() == tokens.Guara.C500


class TestBevelEdges:
    def test_the_top_is_lit_and_the_bottom_is_shaded(self) -> None:
        base = Color(100, 100, 100)

        top, bottom = bevel_edges(base)

        assert top.r > base.r
        assert bottom.r < base.r

    def test_pressing_swaps_them(self) -> None:
        base = Color(100, 100, 100)

        normal = bevel_edges(base)
        pressed = bevel_edges(base, pressed=True)

        assert pressed == (normal[1], normal[0])

    def test_the_edges_are_opaque(self) -> None:
        """Alpha overlays do not work through `pygame.draw`; see skin.py."""
        top, bottom = bevel_edges(Color(100, 100, 100))

        assert (top.a, bottom.a) == (255, 255)


class TestDrawingTheBevel:
    def test_it_draws_inside_the_element(self, renderer: Any) -> None:
        """A bevel that grew the element would break every layout."""
        rect = Rect(10, 20, 100, 40)

        draw_bevel(renderer, rect, Color(100, 100, 100))

        drawn = [call.args[0] for call in renderer.draw_rect.call_args_list]
        assert len(drawn) == 2
        for edge in drawn:
            assert edge.x >= rect.x
            assert edge.y >= rect.y
            assert edge.y + edge.height <= rect.y + rect.height

    def test_thickness_cannot_make_the_edges_overlap(self, renderer: Any) -> None:
        rect = Rect(0, 0, 100, 4)

        draw_bevel(renderer, rect, Color(100, 100, 100), thickness=10)

        top, bottom = (call.args[0] for call in renderer.draw_rect.call_args_list)
        assert top.y + top.height <= bottom.y

    def test_a_stamp_shadow_sits_down_and_right(self, renderer: Any) -> None:
        rect = Rect(10, 10, 50, 20)

        draw_stamp_shadow(renderer, rect, Color.BLACK, offset=3)

        shadow = renderer.draw_rect.call_args.args[0]
        assert (shadow.x, shadow.y) == (13, 13)
        assert (shadow.width, shadow.height) == (50, 20)


class TestBevelButton:
    def test_without_a_skin_it_follows_the_theme(self, dusk: None) -> None:
        button = BevelButton("Play", Vector2(0, 0))

        assert button.fill_color() == cerrado_dusk().colors.action_primary

    def test_a_skin_replaces_the_state_colours(self) -> None:
        button = BevelButton("Play", Vector2(0, 0), skin=Skins.SAGE)

        assert button.fill_color() == Skins.SAGE.fill
        button.state = UIElementState.HOVERED
        assert button.fill_color() == Skins.SAGE.hover
        button.state = UIElementState.PRESSED
        assert button.fill_color() == Skins.SAGE.press

    def test_each_skin_presses_to_its_own_colour(self) -> None:
        """The original turned every variant orange on click, because the
        press colour came from the theme's primary action regardless."""
        sage = BevelButton("a", Vector2(0, 0), skin=Skins.SAGE)
        wood = BevelButton("b", Vector2(0, 0), skin=Skins.WOOD)
        sage.state = wood.state = UIElementState.PRESSED

        assert sage.fill_color() != wood.fill_color()

    def test_disabled_falls_back_to_the_theme(self, dusk: None) -> None:
        """A skin describes a live button; disabled is a theme-wide look."""
        button = BevelButton("Play", Vector2(0, 0), skin=Skins.WOOD)
        button.state = UIElementState.DISABLED

        assert button.fill_color() == cerrado_dusk().colors.action_disabled

    def test_focus_beats_the_skins_edge(self, dusk: None) -> None:
        button = BevelButton("Play", Vector2(0, 0), skin=Skins.WOOD)
        button.state = UIElementState.FOCUSED
        button.focus_visible = True

        assert button.border_color() == cerrado_dusk().colors.focus_ring

    def test_the_label_is_upper_cased_at_render_time(
        self, renderer: Any, dusk: None
    ) -> None:
        """`self.text` keeps what the caller passed -- upper-casing it in
        the constructor threw the original away."""
        button = BevelButton("Play", Vector2(0, 0))

        button.render(renderer)

        assert button.text == "Play"
        assert renderer.draw_text.call_args.args[0] == "PLAY"

    def test_uppercase_can_be_turned_off(self, renderer: Any, dusk: None) -> None:
        button = BevelButton("Play", Vector2(0, 0), uppercase=False)

        button.render(renderer)

        assert renderer.draw_text.call_args.args[0] == "Play"

    def test_a_pressed_button_drops_and_loses_its_shadow(
        self, renderer: Any, dusk: None
    ) -> None:
        button = BevelButton("Play", Vector2(10, 10), Vector2(100, 40))
        button.state = UIElementState.PRESSED

        button.render(renderer)

        faces = [call.args[0] for call in renderer.draw_rect.call_args_list]
        # No shadow: the first rect drawn is the face itself, at the offset.
        assert faces[0].y == 11
        assert renderer.draw_text.call_args.args[1].y > 10

    def test_an_unpressed_button_draws_its_shadow_first(
        self, renderer: Any, dusk: None
    ) -> None:
        button = BevelButton("Play", Vector2(10, 10), Vector2(100, 40))

        button.render(renderer)

        shadow = renderer.draw_rect.call_args_list[0].args[0]
        assert (shadow.x, shadow.y) == (12, 12)

    def test_a_disabled_button_has_no_bevel(self, renderer: Any, dusk: None) -> None:
        """A raised edge on something you cannot press is a lie."""
        button = BevelButton("Play", Vector2(0, 0))
        button.state = UIElementState.DISABLED

        button.render(renderer)

        # Face + border only -- no shadow (disabled is not raised), no bevel.
        assert renderer.draw_rect.call_count == 2


class TestBevelPanel:
    def test_it_bevels_over_the_stock_panel(self, renderer: Any, dusk: None) -> None:
        panel = BevelPanel(Vector2(0, 0), Vector2(100, 50))

        panel.render(renderer)

        # Panel's own fill + border, then the two bevel edges.
        assert renderer.draw_rect.call_count == 4

    def test_the_bevel_can_be_turned_off(self, renderer: Any, dusk: None) -> None:
        panel = BevelPanel(Vector2(0, 0), Vector2(100, 50), bevel=False)

        panel.render(renderer)

        assert renderer.draw_rect.call_count == 2

    def test_the_shadow_is_opt_in(self, renderer: Any, dusk: None) -> None:
        """Every panel carrying a shadow reads as noise, so it is off."""
        with_shadow = BevelPanel(Vector2(0, 0), Vector2(100, 50), shadow=True)

        with_shadow.render(renderer)

        assert renderer.draw_rect.call_count == 5
