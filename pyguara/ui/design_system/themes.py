"""The Cerrado themes: brand tokens mapped onto the engine's semantic roles.

Each theme is an ordinary `UITheme`, so `set_theme(cerrado_dusk())` re-skins
every stock component -- buttons, panels, sliders, the lot -- with no
design-system class involved. That is the whole point of the mapping living
here rather than in a parallel widget tree.

The two schemes are complementary rather than a light/dark pair of the same
numbers: dusk is built on `Roxo` violets with a Guará action, day on `Sand`
earth with a deeper Guará that survives a bright background.
"""

from __future__ import annotations

from pyguara.common.types import Color
from pyguara.ui.design_system.tokens import Falcao, Guara, Roxo, Sand, Wood
from pyguara.ui.theme import UITheme
from pyguara.ui.types import (
    BorderScheme,
    ColorScheme,
    FontScheme,
    ShadowScheme,
    SpacingScheme,
)

FONT_FAMILY = "Arial"
"""Until the brand face ships as a bundled resource, the stock family."""


def _cerrado_fonts() -> FontScheme:
    """The type scale both themes share."""
    return FontScheme(
        family=FONT_FAMILY,
        size_small=12,
        size_normal=16,
        size_large=24,
        size_title=32,
    )


def cerrado_dusk() -> UITheme:
    """The dark theme: violet ground, Guará action, sand focus ring.

    Returns:
        A fresh theme instance -- mutate it freely.
    """
    colors = ColorScheme.derive(
        # Base five, so anything reading the old shorthand still resolves.
        primary=Guara.C500,
        secondary=Sand.C500,
        background=Color.from_hex("#1d1620"),
        text=Color.from_hex("#f2e6d2"),
        border=Color.from_hex("#493a52"),
        # Roles the design team specified outright rather than by rule.
        surface_canvas=Color.from_hex("#1d1620"),
        surface_card=Color.from_hex("#271d2b"),
        surface_raised=Color.from_hex("#332639"),
        surface_inset=Color.from_hex("#17111b"),
        text_heading=Sand.C100,
        text_body=Color.from_hex("#f2e6d2"),
        text_muted=Color.from_hex("#b9a3ad"),
        text_faint=Color.from_hex("#87707f"),
        text_on_primary=Wood.INK_900,
        text_on_disabled=Color.from_hex("#87707f"),
        edge=Color.from_hex("#493a52"),
        edge_strong=Color.from_hex("#6b5578"),
        focus_ring=Sand.C300,
        action_primary=Guara.C500,
        action_primary_hover=Guara.C400,
        action_primary_press=Guara.C600,
        action_secondary=Sand.C500,
        action_disabled=Color.from_hex("#352b3a"),
    )
    return UITheme(
        name="cerrado_dusk",
        colors=colors,
        spacing=SpacingScheme(padding=8, margin=4, gap=8),
        fonts=_cerrado_fonts(),
        borders=BorderScheme(width=2, radius=0, color=colors.edge_strong),
        shadows=ShadowScheme(
            enabled=True,
            offset_x=2,
            offset_y=2,
            blur=0,
            color=Roxo.C900,
        ),
    )


def cerrado_day() -> UITheme:
    """The light theme: sand ground, deepened Guará, wood secondary.

    Returns:
        A fresh theme instance -- mutate it freely.
    """
    colors = ColorScheme.derive(
        primary=Guara.C600,
        secondary=Wood.C400,
        background=Color.from_hex("#f4dda8"),
        text=Wood.C700,
        border=Color.from_hex("#e0bf8a"),
        surface_canvas=Color.from_hex("#f4dda8"),
        surface_card=Color.from_hex("#fef5df"),
        surface_raised=Color.WHITE,
        surface_inset=Color.from_hex("#f4dda8"),
        text_heading=Roxo.C900,
        text_body=Wood.C700,
        text_muted=Color.from_hex("#64352b"),
        text_faint=Wood.C500,
        text_on_primary=Sand.C100,
        text_on_disabled=Color.from_hex("#9b7c58"),
        edge=Color.from_hex("#e0bf8a"),
        edge_strong=Color.from_hex("#bb8b52"),
        # Not the Guará the day theme's primary action is already wearing:
        # a focus ring the same colour as the fill it surrounds is not a
        # focus ring. Ink reads against both the action and the sand.
        focus_ring=Wood.C700,
        action_primary=Guara.C600,
        action_primary_hover=Guara.C500,
        action_primary_press=Guara.C700,
        action_secondary=Wood.C400,
        action_disabled=Color.from_hex("#e0bf8a"),
    )
    return UITheme(
        name="cerrado_day",
        colors=colors,
        spacing=SpacingScheme(padding=8, margin=4, gap=8),
        fonts=_cerrado_fonts(),
        borders=BorderScheme(width=2, radius=0, color=colors.edge_strong),
        shadows=ShadowScheme(
            enabled=True,
            offset_x=2,
            offset_y=2,
            blur=0,
            color=Falcao.C400,
        ),
    )
