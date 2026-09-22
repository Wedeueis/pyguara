"""The weather catalogue, and the live effect the current one has.

Five conditions, each a `WeatherCondition` -- static data, the same shape
`species.py`'s `Species` and `structures.py`'s `Structure` already use for
their own catalogues. `WeatherState` is the other half: a small, mutable,
non-ECS struct (the same "plain data, no individual identity" reasoning
`components.py`'s module docstring gives `SoilCell`) that `WeatherSystem`
recomputes from whichever condition is current, and that `SoilSystem`,
`PestSystem` and `PlantGrowthSystem` each read a couple of fields from --
none of them need to know a `WeatherCondition` or `WEATHER_TABLE` exists at
all, only the handful of multipliers `WeatherState` exposes.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.random import RandomStream
from pyguara.common.types import Color
from pyguara.ui.design_system.tokens import Guara, Sand, Verdant, Water


@dataclass(frozen=True)
class WeatherCondition:
    """One weather condition's static data.

    Attributes:
        condition_id: Stable id, matching `WeatherState.condition_id`.
        display_name: What the forecast panel calls it.
        color: A swatch for the forecast panel (this demo ships no icons).
        weight: Relative likelihood `roll_condition` gives it -- not a
            probability itself, just compared against the others' weights.
        growth_multiplier: Applied on top of everything else
            `PlantGrowthSystem` already multiplies in.
        moisture_gain_per_second: What rain adds to every tilled cell,
            read by `SoilSystem` alongside its own evaporation.
        evaporation_multiplier: Applied to `SoilSystem.EVAPORATION_RATE` --
            wind dries the plot out faster.
        pest_spread_multiplier: Applied to `PestSystem.SPREAD_RATE`.
        cold_snap: Whether this condition stalls growth outright on any
            cell `ShadeSystem` has not covered -- see
            `PlantGrowthSystem`'s own `COLD_SNAP_SHADE_COVER` check. The
            PRD's "cover the canopy gap" is this flag, not a number.
    """

    condition_id: str
    display_name: str
    color: Color
    weight: float = 1.0
    growth_multiplier: float = 1.0
    moisture_gain_per_second: float = 0.0
    evaporation_multiplier: float = 1.0
    pest_spread_multiplier: float = 1.0
    cold_snap: bool = False


CALM_CONDITION_ID = "calm"
"""What a fresh garden starts on, deliberately rather than rolled -- see
`WeatherSystem`'s own docstring for why a random starting condition would
have been the wrong call. A real, ordinary member of the rotation once the
first roll does happen, not a sentinel: its fields are `WeatherCondition`'s
own defaults, so starting on it is identical to no weather system existing
at all, which is exactly the point."""

WEATHER_TABLE: dict[str, WeatherCondition] = {
    CALM_CONDITION_ID: WeatherCondition(
        condition_id=CALM_CONDITION_ID,
        display_name="Calm",
        color=Sand.C100,
        weight=20.0,
    ),
    "clear": WeatherCondition(
        condition_id="clear",
        display_name="Clear",
        color=Sand.C200,
        weight=30.0,
        growth_multiplier=1.15,
    ),
    "cloudy": WeatherCondition(
        condition_id="cloudy",
        display_name="Cloudy",
        color=Verdant.SAGE_100,
        weight=25.0,
        growth_multiplier=0.9,
    ),
    "rainy": WeatherCondition(
        condition_id="rainy",
        display_name="Rain",
        color=Water.C300,
        weight=20.0,
        moisture_gain_per_second=0.02,
    ),
    "windy": WeatherCondition(
        condition_id="windy",
        display_name="Windy",
        color=Verdant.COLONIAL_500,
        weight=15.0,
        evaporation_multiplier=1.8,
        pest_spread_multiplier=1.4,
    ),
    "cold_snap": WeatherCondition(
        condition_id="cold_snap",
        display_name="Cold Snap",
        color=Guara.CREAM,
        weight=10.0,
        growth_multiplier=0.7,
        cold_snap=True,
    ),
}


@dataclass
class WeatherState:
    """The current condition's live effect, read every tick by three
    other systems and not one entity -- see the module docstring for why
    this is plain data rather than a component. Owned and overwritten
    wholesale by `WeatherSystem`; everything else only ever reads it."""

    condition_id: str = CALM_CONDITION_ID
    growth_multiplier: float = 1.0
    moisture_gain_per_second: float = 0.0
    evaporation_multiplier: float = 1.0
    pest_spread_multiplier: float = 1.0
    cold_snap: bool = False


def roll_condition(rng: RandomStream) -> str:
    """Pick a condition, weighted by `WeatherCondition.weight`.

    Args:
        rng: The stream to roll on.

    Returns:
        A `condition_id` from `WEATHER_TABLE`.
    """
    candidates = list(WEATHER_TABLE.values())
    roll = rng.uniform(0.0, sum(c.weight for c in candidates))
    upto = 0.0
    for condition in candidates:
        upto += condition.weight
        if roll <= upto:
            return condition.condition_id
    return candidates[-1].condition_id  # pragma: no cover -- float-rounding fallback
