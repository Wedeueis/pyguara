"""Soil nutrients: four levers, one distinct effect each.

The point is **not** bookkeeping. Every nutrient here earns its place by
owning exactly one effect nothing else owns, and by being something the
player can move on purpose:

| Nutrient | What it does | Where it comes from |
|---|---|---|
| **N** nitrogen | grows the crop faster -- *forced past its band, growth goes soft and pests take hold* | legumes fix it; compost |
| **P** phosphorus | the harvest is worth more | compost |
| **K** potassium | shields growth from cold snaps and dry ground | a deep-rooted canopy tree lifts it |
| **Ca** calcium | multiplies how much a comfortable plant resists pests | a grown Pequi leaves it behind |

The tension is deliberate: nitrogen is the obvious lever, and pushing it
past what the plant wants is exactly what makes pests easy
(`stress.NUTRITION`). A plot that grows fast and stays healthy is one
where the player fed it to the top of the band and no further, and put a
Pequi where its calcium would do the most good -- the syntropic
consortium the PRD is about, arrived at through the soil rather than
announced.

What pests actually meet is in `stress.py`: this module owns the levels,
that one owns what a plant makes of them.

A fifth nutrient only earns a place if it owns an effect none of these
four do. Tracking calcium *and* magnesium because real soil has both is
the spreadsheet this game is trying not to be.

Nothing here is shown as a number. The HUD reads `scarcest` and
`vitality`: "low in nitrogen", or a tile that looks tired.
"""

from __future__ import annotations

from dataclasses import dataclass

from games.quintal_cerrado.components import SoilCell

NITROGEN = "nitrogen"
PHOSPHORUS = "phosphorus"
POTASSIUM = "potassium"
CALCIUM = "calcium"

NUTRIENTS = (NITROGEN, PHOSPHORUS, POTASSIUM, CALCIUM)
"""Every nutrient, in the order the soil readout names them."""


@dataclass(frozen=True)
class Nutrient:
    """One nutrient and the single thing it governs.

    Attributes:
        key: The `SoilCell` field it lives in.
        label: What the HUD calls it.
        short: The one-letter form, for a chip.
        effect: What being rich in it does, in the player's words.
    """

    key: str
    label: str
    short: str
    effect: str


NUTRIENT_TABLE: dict[str, Nutrient] = {
    NITROGEN: Nutrient(NITROGEN, "Nitrogénio", "N", "grows faster, but draws pests"),
    PHOSPHORUS: Nutrient(PHOSPHORUS, "Fósforo", "P", "the harvest is worth more"),
    POTASSIUM: Nutrient(POTASSIUM, "Potássio", "K", "shrugs off cold and drought"),
    CALCIUM: Nutrient(CALCIUM, "Cálcio", "Ca", "resists pests taking hold"),
}

RICH = 0.6
"""At or above this, a nutrient's benefit is in full."""

POOR = 0.2
"""Below this, the soil is short of it and the HUD says so. Fresh ground
starts above it: untouched soil is ordinary, not deficient, and a bed only
reads as hungry once it has actually been worked."""

GROWTH_BONUS = 0.4
"""How much faster a crop grows on nitrogen-rich soil."""

VALUE_BONUS = 0.3
"""How much more a harvest fetches from phosphorus-rich soil."""

COLD_GUARD = 0.5
"""How much of a cold snap's and dry ground's penalty potassium spares."""


def level(soil: SoilCell, nutrient: str) -> float:
    """How much of `nutrient` a cell holds, 0.0-1.0.

    Args:
        soil: The cell.
        nutrient: A key of `NUTRIENT_TABLE`.

    Returns:
        The level, or 0.0 for an unknown nutrient.
    """
    return float(getattr(soil, nutrient, 0.0))


def _fraction(value: float) -> float:
    """How far `value` sits between `POOR` and `RICH`, clamped to 0-1."""
    if value <= POOR:
        return 0.0
    return min(1.0, (value - POOR) / (RICH - POOR))


def growth_multiplier(soil: SoilCell) -> float:
    """What the soil's nitrogen does to a plant's growth rate."""
    return 1.0 + GROWTH_BONUS * _fraction(level(soil, NITROGEN))


def value_multiplier(soil: SoilCell) -> float:
    """What the soil's phosphorus adds to a harvest's price."""
    return 1.0 + VALUE_BONUS * _fraction(level(soil, PHOSPHORUS))


def hardiness(soil: SoilCell) -> float:
    """How much of a cold or dry penalty the soil's potassium spares, 0-1."""
    return COLD_GUARD * _fraction(level(soil, POTASSIUM))


def calcium_share(soil: SoilCell) -> float:
    """How far this cell's calcium has come, 0.0-1.0.

    What `stress.pest_resistance` multiplies by a plant's comfort: calcium
    is conditioning, not a shield, so what it is worth depends on the
    plant being in a state to use it.
    """
    return _fraction(level(soil, CALCIUM))


def vitality(soil: SoilCell) -> float:
    """One reading of how well-fed the soil is, 0.0-1.0.

    The derived value the HUD shows instead of four bars -- and the answer
    to "do we need to track every element separately": no, the player
    needs to know whether the ground is in good heart and what it is short
    of.
    """
    return sum(min(1.0, level(soil, key)) for key in NUTRIENTS) / len(NUTRIENTS)


def scarcest(soil: SoilCell) -> Nutrient | None:
    """The nutrient this cell is shortest of, or None if none is low.

    Args:
        soil: The cell.

    Returns:
        The `Nutrient` below `POOR` with the lowest level, or None.
    """
    low = [key for key in NUTRIENTS if level(soil, key) < POOR]
    if not low:
        return None
    return NUTRIENT_TABLE[min(low, key=lambda key: level(soil, key))]
