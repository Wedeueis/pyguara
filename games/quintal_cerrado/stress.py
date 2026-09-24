"""How comfortable a plant is, and what that buys it against pests.

Pests used to land on whatever was nearest, and the only defence was
calcium in the soil. That made an outbreak something done *to* the player
rather than something the garden could be arranged to resist. Here, a
plant that is well fed, well watered, standing in the light it wants and
out of the cold is hard for pests to take -- and a stressed one is easy.

**Every factor has an ideal band, not a ceiling.** Too much is as bad as
too little: a parched bed is stressed, and so is a waterlogged one; a
starved plant is stressed, and so is one forced on so much nitrogen that
it puts out soft, lush growth aphids love. This is the honest version of
"good conditions": gardening is not a bar you fill to the top.

**A plant is only as comfortable as its worst condition.** Comfort is the
*minimum* of the factors, not their average -- Liebig's law of the
minimum, the same agronomy the rest of this game is built on. Drowning a
plant is not offset by feeding it well.

**Calcium multiplies what comfort already earned.** It is a conditioning
nutrient, not a shield: a thriving plant uses it to resist an outbreak
outright, and a dying one barely notices it. That keeps calcium worth
planting a Pequi for without turning it into an answer to neglect.
"""

from __future__ import annotations

from dataclasses import dataclass

from games.quintal_cerrado import nutrients
from games.quintal_cerrado.components import SoilCell
from games.quintal_cerrado.species import Species
from games.quintal_cerrado.weather import WeatherState


@dataclass(frozen=True)
class Band:
    """The range of a condition a plant is happy in.

    Attributes:
        low: Below this, comfort has fallen to zero.
        ideal_low: The bottom of the comfortable range.
        ideal_high: The top of it.
        high: Above this, comfort has fallen to zero again.
    """

    low: float
    ideal_low: float
    ideal_high: float
    high: float

    def comfort(self, value: float) -> float:
        """How comfortable `value` is in this band, 0.0-1.0."""
        if self.ideal_low <= value <= self.ideal_high:
            return 1.0
        if value < self.ideal_low:
            span = self.ideal_low - self.low
            return max(0.0, (value - self.low) / span) if span > 0 else 0.0
        span = self.high - self.ideal_high
        return max(0.0, (self.high - value) / span) if span > 0 else 0.0


MOISTURE = Band(0.05, 0.4, 0.85, 1.0)
"""Dry ground stalls growth outright; sodden ground merely stresses."""

NUTRITION = Band(0.05, 0.35, 0.8, 1.05)
"""Fresh ground (0.35) is already comfortable. The top of the band is what
makes nitrogen a lever with a cost: forced past it, growth goes soft and
pests take hold more easily."""

_LIGHT_BANDS = {
    "canopy": Band(-1.0, 0.0, 0.35, 0.9),
    "understory": Band(-0.6, 0.25, 0.85, 1.2),
    "ground_cover": Band(-1.0, 0.0, 0.65, 1.1),
}
"""What each layer wants overhead. A canopy tree wants the sun it is
growing towards; an understory plant wants the shade of one. This is the
stratification the PRD asks for, stated as a comfort rather than a bonus.

The bands reach past 0 and 1 on purpose. An understory plant in the open
is less comfortable than one under a canopy, but it is not *ruined* --
early on, before any tree has grown, everything is planted in full sun,
and a band that bottomed out there would make the opening of every
session a pest magnet."""

COLD_COMFORT = 0.25
"""How comfortable an exposed plant is during a cold snap. Shade cover or
potassium (`nutrients.hardiness`) lift it back towards warm."""

BASE_RESISTANCE = 0.55
"""How much of an arriving outbreak a perfectly comfortable plant turns
away on its own, before calcium."""

CALCIUM_RESISTANCE = 0.35
"""What calcium adds on top -- multiplied by comfort, so it is worth most
to a plant that is already doing well."""

MIN_SUSCEPTIBILITY = 0.1
"""However ideal the conditions, some pressure always lands: a garden is
defensible, not immune."""


@dataclass(frozen=True)
class Comfort:
    """A plant's conditions, factor by factor.

    Attributes:
        moisture: Comfort with the water it has.
        nutrition: Comfort with what it is being fed.
        light: Comfort with the light reaching it.
        warmth: Comfort with the weather.
        overall: The worst of them -- what the plant actually feels.
        worst: Which factor that was.
    """

    moisture: float
    nutrition: float
    light: float
    warmth: float
    overall: float
    worst: str


def comfort(
    soil: SoilCell, species: Species | None = None, weather: WeatherState | None = None
) -> Comfort:
    """How well `soil` suits a plant of `species` under `weather`.

    Args:
        soil: The cell the plant stands in.
        species: What is growing there, for the light it wants. None reads
            as a middling appetite for light.
        weather: The sky, for the cold. None reads as calm.

    Returns:
        Every factor, and the worst of them.
    """
    factors = {
        "water": MOISTURE.comfort(soil.moisture),
        "food": _nutrition(soil),
        "light": _light(soil, species),
        "warmth": _warmth(soil, weather),
    }
    worst = min(factors, key=lambda key: factors[key])
    return Comfort(
        moisture=factors["water"],
        nutrition=factors["food"],
        light=factors["light"],
        warmth=factors["warmth"],
        overall=factors[worst],
        worst=worst,
    )


def _nutrition(soil: SoilCell) -> float:
    """Comfort with nitrogen and phosphorus, whichever is further off."""
    return min(
        NUTRITION.comfort(soil.nitrogen),
        NUTRITION.comfort(soil.phosphorus),
    )


def _light(soil: SoilCell, species: Species | None) -> float:
    """Comfort with the shade over the cell, for what is growing in it."""
    layer = species.canopy_layer if species is not None else "ground_cover"
    band = _LIGHT_BANDS.get(layer, _LIGHT_BANDS["ground_cover"])
    return band.comfort(soil.shade_level)


def _warmth(soil: SoilCell, weather: WeatherState | None) -> float:
    """Comfort with the weather: only a cold snap is uncomfortable.

    Cover and potassium both answer it, the same two things that let a
    plant keep growing through one (`plant_growth_system.py`).
    """
    if weather is None or not weather.cold_snap:
        return 1.0
    # Cover can shelter a plant completely; potassium only ever softens
    # the cold (`nutrients.COLD_GUARD` caps it at half), so a canopy is
    # still the answer and well-fed ground is the consolation.
    sheltered = max(soil.shade_level, nutrients.hardiness(soil))
    return min(1.0, COLD_COMFORT + (1.0 - COLD_COMFORT) * sheltered)


_PHRASES = {
    ("water", "low"): "thirsty",
    ("water", "high"): "waterlogged",
    ("food", "low"): "hungry",
    ("food", "high"): "forced",
    ("light", "low"): "wants shade",
    ("light", "high"): "wants sun",
    ("warmth", "low"): "cold",
}
"""How each way of being uncomfortable reads to the player. Two per
factor, because a band has two sides: "forced" is a plant pushed past
what it wants, not one that is short of anything."""

THRIVING = "thriving"
"""What a plant with nothing wrong with it is called."""

CONTENT_ENOUGH = 0.75
"""Above this, a plant is thriving and the HUD says nothing else."""


def describe(
    soil: SoilCell, species: Species | None = None, weather: WeatherState | None = None
) -> str:
    """One word for how a plant here is doing.

    What the cell inspector shows instead of four readings: the single
    thing most worth doing something about.

    Args:
        soil: The cell.
        species: What grows there.
        weather: The sky.

    Returns:
        `"thriving"`, or the worst thing about its conditions.
    """
    state = comfort(soil, species, weather)
    if state.overall >= CONTENT_ENOUGH:
        return THRIVING
    side = "high" if _above_band(soil, species, state.worst) else "low"
    return _PHRASES.get((state.worst, side), THRIVING)


def _above_band(soil: SoilCell, species: Species | None, factor: str) -> bool:
    """Whether `factor` is uncomfortable for being too *much*."""
    if factor == "water":
        return soil.moisture > MOISTURE.ideal_high
    if factor == "food":
        return min(soil.nitrogen, soil.phosphorus) > NUTRITION.ideal_high
    if factor == "light":
        layer = species.canopy_layer if species is not None else "ground_cover"
        band = _LIGHT_BANDS.get(layer, _LIGHT_BANDS["ground_cover"])
        return soil.shade_level > band.ideal_high
    return False


def pest_resistance(
    soil: SoilCell, species: Species | None = None, weather: WeatherState | None = None
) -> float:
    """How much arriving pest pressure this plant turns away, 0.0-1.0.

    Args:
        soil: The cell.
        species: What grows there.
        weather: The sky.

    Returns:
        The share of pressure resisted.
    """
    ease = comfort(soil, species, weather).overall
    calcium = nutrients.calcium_share(soil)
    return min(
        1.0 - MIN_SUSCEPTIBILITY,
        ease * (BASE_RESISTANCE + CALCIUM_RESISTANCE * calcium),
    )


def pest_susceptibility(
    soil: SoilCell, species: Species | None = None, weather: WeatherState | None = None
) -> float:
    """What fraction of arriving pest pressure actually lands here.

    Args:
        soil: The cell.
        species: What grows there.
        weather: The sky.

    Returns:
        A multiplier on the pressure reaching this cell.
    """
    return max(MIN_SUSCEPTIBILITY, 1.0 - pest_resistance(soil, species, weather))
