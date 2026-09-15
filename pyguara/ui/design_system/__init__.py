"""The PyGuara design system: brand tokens, themes, and the Cerrado look.

Three layers, deliberately separable:

- `tokens` -- the brand palette. Raw colours, no opinion about use.
- `themes` -- `cerrado_dusk()` / `cerrado_day()`, ordinary `UITheme`s that
  map those tokens onto the engine's semantic colour roles.
- `components` / `skin` -- the little that a theme cannot express: a
  bevelled edge, a stamp shadow, and the brand's button colourways.

The usual way in is the theme alone::

    from pyguara.ui import set_theme
    from pyguara.ui.design_system import cerrado_dusk

    set_theme(cerrado_dusk())

which re-skins every stock component -- panels, buttons, sliders, fields --
because they read the same roles the theme defines. Reach for `BevelButton`
or `BevelPanel` only where you want the raised edge as well.
"""

from pyguara.ui.design_system.components import (
    BevelButton,
    BevelPanel,
    ButtonSkin,
    Skins,
)
from pyguara.ui.design_system.skin import (
    bevel_edges,
    draw_bevel,
    draw_stamp_shadow,
)
from pyguara.ui.design_system.themes import cerrado_day, cerrado_dusk
from pyguara.ui.design_system.tokens import (
    Falcao,
    Guara,
    Rock,
    Roxo,
    Sand,
    Verdant,
    Water,
    Wood,
)

__all__ = [
    # Themes
    "cerrado_dusk",
    "cerrado_day",
    # Components
    "BevelButton",
    "BevelPanel",
    "ButtonSkin",
    "Skins",
    # Skin helpers
    "draw_bevel",
    "draw_stamp_shadow",
    "bevel_edges",
    # Tokens
    "Guara",
    "Sand",
    "Rock",
    "Wood",
    "Verdant",
    "Roxo",
    "Water",
    "Falcao",
]
