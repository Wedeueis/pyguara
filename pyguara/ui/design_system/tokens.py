"""The PyGuara brand palette: raw colour values, no semantics.

These are the design team's named colours, one family per block, each with
the hex the palette was specified in. Nothing here says what a colour is
*for* -- `themes.py` does that, mapping these onto the semantic roles in
`ColorScheme` (a surface, an edge, a pressed action). Keeping the two apart
is what lets a colour be renamed or re-tuned in one place, and what stops a
component from reaching for "the orange one".

Identifiers are ASCII: the family is Guará, but `GUARA_500` is what you can
type, grep and import without an encoding accident. (The palette arrived
with the accent inside the identifier, which is why this note exists.)

Component *dimensions* deliberately live nowhere near here. The palette
originally carried a metrics block -- 120x40 buttons, 20px checkboxes,
200x20 progress bars, a 50px navbar -- and every number in it already
matched the corresponding engine component's default. Two copies of the
same number is a drift waiting to happen, so the components keep theirs.
"""

from __future__ import annotations

from pyguara.common.types import Color


class Guara:
    """The primary brand family: the maned wolf's red-orange coat."""

    C400 = Color.from_hex("#ec7225")
    C500 = Color.from_hex("#e2621f")
    C600 = Color.from_hex("#b94a15")
    C700 = Color.from_hex("#8a3512")
    CREAM = Color.from_hex("#fccc85")


class Sand:
    """Cerrado earth, from bleached grass down to dry season dust."""

    C100 = Color.from_hex("#fdecbe")
    C200 = Color.from_hex("#fde3a9")
    C300 = Color.from_hex("#fad373")
    C400 = Color.from_hex("#fac375")
    C500 = Color.from_hex("#dfa33f")


class Rock:
    """Ironstone and termite mound."""

    C600 = Color.from_hex("#944639")


class Wood:
    """Worked wood and the ink end of the range."""

    C400 = Color.from_hex("#bb6c3e")
    C500 = Color.from_hex("#8c5135")
    C700 = Color.from_hex("#3b1c14")
    INK_900 = Color.from_hex("#1e120c")


class Verdant:
    """Sage scrub and colonial green: the vegetation half of the palette."""

    SAGE_100 = Color.from_hex("#dfe6cf")
    SAGE_500 = Color.from_hex("#656d49")
    COLONIAL_500 = Color.from_hex("#3f6b4c")
    COLONIAL_700 = Color.from_hex("#24382e")


class Roxo:
    """Dusk ground and accents -- the violet the night themes are built on."""

    C300 = Color.from_hex("#c39ad6")
    C500 = Color.from_hex("#7a4c9e")
    C700 = Color.from_hex("#3c2452")
    C900 = Color.from_hex("#241531")


class Water:
    """Standing water and glass."""

    C300 = Color.from_hex("#8fd3d2")
    C400 = Color.from_hex("#64b5ae")


class Falcao:
    """Falcão slate: the neutral that is not quite grey."""

    C400 = Color.from_hex("#7c7b86")
