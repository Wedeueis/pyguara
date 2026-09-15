# UI Design System

The PyGuara design system is **content for the UI system, not a second one**.
It is a brand palette, two themes built from it, and the two pieces of
drawing a theme cannot express. Every stock component -- `Button`, `Panel`,
`Checkbox`, `Slider`, `ProgressBar`, `TextInput` -- renders in the design
system's colours without knowing it exists, because they read the same
semantic roles the themes define.

```python
from pyguara.ui import set_theme
from pyguara.ui.design_system import cerrado_dusk

set_theme(cerrado_dusk())
```

That is the whole integration. Two themes ship: `cerrado_dusk()` (violet
ground, Guará action) and `cerrado_day()` (sand ground, deepened Guará).
Each call returns a fresh `UITheme`, so mutating one never affects the next
caller.

## Semantic colour roles

`ColorScheme` has two layers. The **base** five -- `primary`, `secondary`,
`background`, `text`, `border` -- are the shorthand themes have always been
written in. The **semantic roles** are what components actually read:

| Group | Roles |
| --- | --- |
| Surfaces | `surface_canvas`, `surface_card`, `surface_raised`, `surface_inset` |
| Text | `text_heading`, `text_body`, `text_muted`, `text_faint`, `text_on_primary`, `text_on_disabled` |
| Edges | `edge`, `edge_strong`, `focus_ring` |
| Actions | `action_primary`, `action_primary_hover`, `action_primary_press`, `action_secondary`, `action_disabled` |

The roles exist because the base five had to be overloaded: `secondary`
meant the accent *and* the hover fill *and* the focus ring *and* a
checkbox's tick, and a placeholder was drawn in the border colour because
it happened to be dim enough. A design system cannot be stated in that
vocabulary.

### Deriving a scheme

Name only what you care about and let the rest follow:

```python
from pyguara.common.types import Color
from pyguara.ui.types import ColorScheme

colors = ColorScheme.derive(
    primary=Color(226, 98, 31),
    background=Color(29, 22, 32),
    text=Color(242, 230, 210),
)
```

Surfaces are lifted by interpolating **towards the theme's text colour**,
which lightens them in a dark theme and darkens them in a light one, so one
rule serves both. `text_on_primary` is chosen by luminance, so a pale action
colour gets dark text. Any role passed explicitly wins over the rule; an
unknown role name raises rather than being silently dropped.

`ColorScheme(...)` still works and still fills every role -- but it fills
them from the *generic* defaults, so a themed palette built that way renders
its buttons in another theme's colours. Prefer `derive()`.

## Tokens

`pyguara.ui.design_system.tokens` holds the brand palette as plain `Color`
values, grouped by family: `Guara`, `Sand`, `Rock`, `Wood`, `Verdant`,
`Roxo`, `Water`, `Falcao`. Nothing there says what a colour is *for* --
`themes.py` does that. Component dimensions deliberately live with the
components, not here.

## What needed code

Two things are geometry rather than colour, so they could not be theme
values:

```python
from pyguara.common.types import Vector2
from pyguara.ui.design_system import BevelButton, BevelPanel, Skins

play = BevelButton("Play", Vector2(40, 40))
sage = BevelButton("Options", Vector2(40, 100), skin=Skins.SAGE)
card = BevelPanel(Vector2(16, 16), Vector2(400, 300), shadow=True)
```

`BevelButton` is the stock `Button` -- same sizing, focus traversal and
click handling -- plus a raised edge that inverts when pressed, a face that
drops a pixel while held, and an upper-cased label applied at render time
(`self.text` keeps what you passed). Without a `skin` it follows the active
theme's action colours, so it stays correct under any theme.

`ButtonSkin` covers the brand colourways that are not "the theme's primary
action": `Skins.SAGE`, `Skins.WOOD`, `Skins.GUARA`. Each carries its own
pressed colour, so a green button does not flash orange on click. A disabled
button ignores its skin and falls back to the theme -- disabled is a
theme-wide look, and it draws neither bevel nor shadow, since it is not
raised.

### Why the bevel is opaque

The obvious bevel is white at low alpha on the top edge and black on the
bottom. It does not work: both UI backends draw through `pygame.draw`, which
**replaces** the destination pixel including its alpha rather than blending.
On the pygame backend the surface is opaque, so a 45/255 white lands as
solid white; on the ModernGL backend the overlay is `SRCALPHA`, so the same
call punches a transparent hole in the element. `bevel_edges()` mixes the
highlight into the fill colour on the CPU instead, which gives the same
result on both backends and is deterministic enough to assert in a test.

## Seeing it work

`games/guara_falcao` is the worked example: a title screen, a HUD, a pause
menu and an options panel, all skinned by `cerrado_dusk()` and none of them
holding a colour of their own.

```bash
uv run python tools/agent_view.py guara_falcao --gl --frames 40 --shot 39
```

It is also where the pieces that are *not* colour get exercised —
`UILayer.HUD` under `UILayer.OVERLAY`, the focus ring scoped to the topmost
layer so Tab cannot leave an open modal, `LayoutConstraints` anchoring the
HUD to the corners, and the options panel's theme row calling `set_theme()`
live, which re-skins the panel the switch is sitting in.
