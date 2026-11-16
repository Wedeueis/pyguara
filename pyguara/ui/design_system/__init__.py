"""The PyGuara design system: brand tokens, themes, and the Cerrado look.

- `tokens`: the brand palette, raw colours.
- `themes`: `cerrado_dusk()` and `cerrado_day()`, ordinary `UITheme`s
  mapping those tokens onto the engine's semantic colour roles.
- `components` and `skin`: a bevelled edge, a stamp shadow and the
  brand's button colourways.

Setting the theme re-skins every stock component. Use `BevelButton`
or `BevelPanel` only where the raised edge is wanted.

Example:
    from pyguara.ui import set_theme
    from pyguara.ui.design_system import cerrado_dusk

    set_theme(cerrado_dusk())
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
