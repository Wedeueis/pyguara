"""The Cerrado's two seasons, over a twelve-day run.

The Cerrado does not have four seasons; it has **a dry one and a wet one**,
and the whole biome is shaped by the swing between them. A twelve-day
session gets three spells of four days -- dry, wet, dry -- so a run opens
in the drought the plot has to be nursed through, opens up in the rains,
and closes dry again with the harvest.

This was parked (#215) while a session was fifteen real minutes, on the
grounds that seasons pay off over a longer horizon than that. Twelve
turn-based days is that horizon: four days is long enough for a spell to
change what the player does, and short enough that all three arrive.

Two levers only, deliberately kept light:

- **the sky**: each season re-weights `weather.roll_condition`, so rain is
  a wet-season thing and the cold fronts (*friagem*) that sweep the Cerrado
  belong to the dry one;
- **the market**: a crop in its own season sells for more, which is the
  reason to plan what goes in the ground around what is coming rather than
  planting whatever is cheapest.

Growth rates are untouched. The weather already moves those through
`WeatherState`, and a second multiplier on top would be two systems saying
the same thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from games.quintal_cerrado.turn import SESSION_DAYS

SEASON_LENGTH = 4
"""Days in one spell. Three of them cover a twelve-day session."""

DRY = "seca"
WET = "aguas"

IN_SEASON_PREMIUM = 1.25
"""What a crop fetches in the season that suits it. Enough to plan around,
not enough to make an out-of-season crop a mistake."""


@dataclass(frozen=True)
class Season:
    """One spell of weather and what it is worth to the market.

    Attributes:
        key: Stable id, used by `Species.season`.
        display_name: What the HUD calls it.
        icon_id: An `icons.ICONS` key for the ribbon.
        blurb: One line for the morning a season turns. Short: the
            morning report prints it after the name, on one row.
        weights: Per-condition multipliers on `WeatherCondition.weight`.
            Anything missing keeps its ordinary weight.
    """

    key: str
    display_name: str
    icon_id: str
    blurb: str
    weights: dict[str, float] = field(default_factory=dict)


SEASON_TABLE: dict[str, Season] = {
    DRY: Season(
        key=DRY,
        display_name="Seca",
        icon_id="clear",
        blurb="Little rain, and cold fronts come through.",
        # No rain at all, more sun and wind, and the friagem that only the
        # dry season brings.
        weights={"rainy": 0.0, "clear": 1.8, "windy": 1.3, "cold_snap": 1.4},
    ),
    WET: Season(
        key=WET,
        display_name="Águas",
        icon_id="rainy",
        blurb="The plot waters itself, and the pests like it too.",
        weights={"rainy": 3.0, "cloudy": 1.6, "cold_snap": 0.0, "clear": 0.6},
    ),
}

_CALENDAR = (DRY, WET, DRY)
"""The run's shape: nursed through a drought, opened up by the rains,
closed dry again for the harvest."""


def season_for(day: int) -> Season:
    """Which season `day` falls in.

    Args:
        day: The day, 1-based. Days past the session's end stay in the
            last spell rather than wrapping.

    Returns:
        The season.
    """
    index = min(len(_CALENDAR) - 1, max(0, (day - 1) // SEASON_LENGTH))
    return SEASON_TABLE[_CALENDAR[index]]


def turns_on(day: int) -> bool:
    """Whether `day` is the first morning of a new season.

    Args:
        day: The day, 1-based.

    Returns:
        Whether the season just changed -- what the morning report asks
        before announcing it.
    """
    return day > 1 and day <= SESSION_DAYS and (day - 1) % SEASON_LENGTH == 0


def condition_weight(season: Season, condition_id: str, weight: float) -> float:
    """What `condition_id` weighs during `season`.

    Args:
        season: The season in force.
        condition_id: The condition being weighted.
        weight: Its ordinary weight.

    Returns:
        The seasonal weight, which may be zero.
    """
    return weight * season.weights.get(condition_id, 1.0)


def price_multiplier(season: Season, species_season: str | None) -> float:
    """What a crop of `species_season` fetches during `season`.

    Args:
        season: The season the harvest happens in.
        species_season: The season that suits the species, or None for one
            that does not care.

    Returns:
        `IN_SEASON_PREMIUM` in its own season, otherwise 1.0.
    """
    if species_season is None or species_season != season.key:
        return 1.0
    return IN_SEASON_PREMIUM
