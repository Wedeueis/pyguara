"""`ColorScheme`'s semantic roles, and the derivation that fills them.

The palette used to be five colours plus two overlays, so a component had
to overload them: `secondary` meant both "the accent" and "hovered" and
"focused", and there was no way to say "the surface a card sits on" at all.
A design system cannot be expressed in that vocabulary, so the roles exist
-- and `derive()` is what keeps a theme that names only the base five from
rendering half its widgets in another palette's colours.
"""

from __future__ import annotations

import pytest

from pyguara.common.types import Color
from pyguara.ui.theme import UITheme
from pyguara.ui.theme_presets import Themes
from pyguara.ui.types import ColorScheme

DARK = {
    "background": Color(32, 32, 32),
    "text": Color(255, 255, 255),
    "primary": Color(70, 130, 180),
}
LIGHT = {
    "background": Color(244, 221, 168),
    "text": Color(59, 28, 20),
    "primary": Color(185, 74, 21),
}


def _luminance(color: Color) -> float:
    return 0.2126 * color.r + 0.7152 * color.g + 0.0722 * color.b


class TestDefaultsAndDerivation:
    def test_the_plain_defaults_are_the_derived_ones(self) -> None:
        """Two ways to spell the same palette must not drift apart."""
        assert ColorScheme() == ColorScheme.derive()

    def test_an_override_wins_over_the_rule(self) -> None:
        scheme = ColorScheme.derive(**DARK, surface_card=Color(1, 2, 3))

        assert scheme.surface_card == Color(1, 2, 3)

    def test_a_role_that_does_not_exist_is_refused(self) -> None:
        """A typo'd role would otherwise be silently dropped."""
        with pytest.raises(TypeError, match="no role"):
            ColorScheme.derive(surfase_card=Color(1, 2, 3))

    def test_the_base_colours_survive_derivation(self) -> None:
        scheme = ColorScheme.derive(**DARK)

        assert scheme.primary == DARK["primary"]
        assert scheme.background == DARK["background"]


class TestSurfacesLiftInEitherDirection:
    """A card is lighter than a dark page and darker than a light one.

    Interpolating towards the theme's *text* colour is what makes one rule
    serve both, rather than a hard-coded "lighten by 6%".
    """

    def test_a_dark_theme_lifts_surfaces_lighter(self) -> None:
        scheme = ColorScheme.derive(**DARK)

        assert _luminance(scheme.surface_card) > _luminance(scheme.surface_canvas)
        assert _luminance(scheme.surface_raised) > _luminance(scheme.surface_card)

    def test_a_light_theme_lifts_surfaces_darker(self) -> None:
        scheme = ColorScheme.derive(**LIGHT)

        assert _luminance(scheme.surface_card) < _luminance(scheme.surface_canvas)
        assert _luminance(scheme.surface_raised) < _luminance(scheme.surface_card)

    @pytest.mark.parametrize("base", [DARK, LIGHT], ids=["dark", "light"])
    def test_an_inset_surface_is_always_darker(self, base: dict[str, Color]) -> None:
        """A trough reads as cut in, whichever way the theme runs."""
        scheme = ColorScheme.derive(**base)

        assert _luminance(scheme.surface_inset) < _luminance(scheme.surface_canvas)


class TestTextHierarchy:
    @pytest.mark.parametrize("base", [DARK, LIGHT], ids=["dark", "light"])
    def test_emphasis_descends_towards_the_background(
        self, base: dict[str, Color]
    ) -> None:
        scheme = ColorScheme.derive(**base)

        body = abs(_luminance(scheme.text_body) - _luminance(scheme.surface_canvas))
        muted = abs(_luminance(scheme.text_muted) - _luminance(scheme.surface_canvas))
        faint = abs(_luminance(scheme.text_faint) - _luminance(scheme.surface_canvas))

        assert body > muted > faint

    def test_text_on_primary_is_picked_for_contrast(self) -> None:
        """Not a fixed white: a sand-coloured action needs dark text."""
        on_dark = ColorScheme.derive(primary=Color(20, 20, 40)).text_on_primary
        on_light = ColorScheme.derive(primary=Color(250, 240, 200)).text_on_primary

        assert on_dark == Color.WHITE
        assert on_light == Color.BLACK


class TestActionStates:
    @pytest.mark.parametrize("base", [DARK, LIGHT], ids=["dark", "light"])
    def test_hover_is_lighter_and_press_is_darker(self, base: dict[str, Color]) -> None:
        scheme = ColorScheme.derive(**base)

        assert _luminance(scheme.action_primary_hover) > _luminance(
            scheme.action_primary
        )
        assert _luminance(scheme.action_primary_press) < _luminance(
            scheme.action_primary
        )


class TestThePresetsDeriveTheirOwnRoles:
    """The regression that caught this: a magenta theme drawing steel-blue.

    Every preset names only its base colours, so building `ColorScheme(...)`
    directly left every semantic role at the *generic* default -- and the
    moment components started reading those roles, a themed button ignored
    its theme.
    """

    @pytest.mark.parametrize(
        "name", ["DARK", "LIGHT", "HIGH_CONTRAST", "CYBERPUNK", "FOREST", "RETRO"]
    )
    def test_the_action_colour_is_the_themes_own(self, name: str) -> None:
        theme = getattr(Themes, name)

        assert theme.colors.action_primary == theme.colors.primary

    def test_cyberpunk_is_magenta_all_the_way_down(self) -> None:
        colors = Themes.CYBERPUNK.colors

        assert colors.action_primary == Color(255, 0, 255)
        assert colors.surface_canvas == colors.background


class TestSerialisation:
    def test_the_roles_survive_a_json_round_trip(self) -> None:
        theme = UITheme(name="t", colors=ColorScheme.derive(**LIGHT))

        restored = UITheme.from_json(theme.to_json())

        assert restored.colors.surface_card == theme.colors.surface_card
        assert restored.colors.action_primary_press == theme.colors.action_primary_press
        assert restored.colors.focus_ring == theme.colors.focus_ring

    def test_a_theme_saved_before_the_roles_existed_still_loads(self) -> None:
        """Old JSON carries only the base five; the rest must fill in."""
        legacy = {
            "name": "legacy",
            "colors": {
                "primary": {"r": 255, "g": 0, "b": 0, "a": 255},
                "background": {"r": 10, "g": 10, "b": 10, "a": 255},
            },
            "spacing": {},
            "fonts": {},
            "borders": {},
            "shadows": {},
        }

        theme = UITheme.from_dict(legacy)

        assert theme.colors.primary == Color(255, 0, 0)
        assert theme.colors.action_primary is not None

    def test_cloning_carries_the_roles(self) -> None:
        theme = UITheme(name="t", colors=ColorScheme.derive(**DARK))

        clone = theme.clone()
        clone.colors.surface_card = Color(9, 9, 9)

        assert theme.colors.surface_card != Color(9, 9, 9)


class TestModalAndStatusRoles:
    """Roles the design system's own token file names, ported in a second
    pass because the showcase needs them: a scrim and an overlay surface for
    modals, a subtle edge for row rules, and the three status colours a
    meter is drawn in."""

    def test_the_scrim_is_translucent(self) -> None:
        """An opaque scrim is not a scrim -- it hides what it should dim."""
        scheme = ColorScheme.derive(**DARK)

        assert 0 < scheme.surface_scrim.a < 255

    def test_the_scrim_is_darker_than_the_canvas(self) -> None:
        scheme = ColorScheme.derive(**LIGHT)

        assert _luminance(scheme.surface_scrim) < _luminance(scheme.surface_canvas)

    def test_an_overlay_is_nearly_solid(self) -> None:
        """A modal surface shows a hint of the scene, not a view of it."""
        scheme = ColorScheme.derive(**DARK)

        assert scheme.surface_overlay.a > scheme.surface_scrim.a

    @pytest.mark.parametrize("base", [DARK, LIGHT], ids=["dark", "light"])
    def test_a_subtle_edge_sits_between_the_surface_and_the_edge(
        self, base: dict[str, Color]
    ) -> None:
        """A row rule that reads as strongly as a border is not a rule."""
        scheme = ColorScheme.derive(**base)

        subtle = abs(_luminance(scheme.edge_subtle) - _luminance(scheme.surface_canvas))
        full = abs(_luminance(scheme.edge) - _luminance(scheme.surface_canvas))
        assert subtle < full

    def test_status_colours_do_not_follow_the_theme(self) -> None:
        """Danger is red because of what red means, not what the theme is."""
        blue = ColorScheme.derive(primary=Color(0, 0, 255))
        green = ColorScheme.derive(primary=Color(0, 255, 0))

        assert blue.state_danger == green.state_danger
        assert blue.state_danger.r > blue.state_danger.b

    def test_a_theme_can_still_state_its_own(self) -> None:
        scheme = ColorScheme.derive(state_danger=Color(1, 2, 3))

        assert scheme.state_danger == Color(1, 2, 3)


class TestTheCerradoThemesCarryThem:
    def test_dusk_uses_the_specified_text_on_primary(self) -> None:
        """Derivation picks ink by luminance; the palette says cream, and
        where the design team states a value it wins over the rule."""
        from pyguara.ui.design_system import cerrado_dusk
        from pyguara.ui.design_system.tokens import Sand

        assert cerrado_dusk().colors.text_on_primary == Sand.C100

    def test_both_themes_carry_a_translucent_scrim(self) -> None:
        from pyguara.ui.design_system import cerrado_day, cerrado_dusk

        for theme in (cerrado_dusk(), cerrado_day()):
            assert 0 < theme.colors.surface_scrim.a < 255
