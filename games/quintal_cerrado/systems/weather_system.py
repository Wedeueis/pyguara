"""Cycles the weather, and keeps a short forecast of what's coming.

Owns nothing but the clock and `WeatherState` itself -- it never touches a
`SoilCell` or a `PlantComponent` directly. `SoilSystem`, `PestSystem` and
`PlantGrowthSystem` each read the couple of `WeatherState` fields that
matter to them (see `weather.py`'s module docstring), so a new weather
effect only ever means adding a field there and a read in the one system
it belongs to -- never a change here.

A fresh garden starts on `CALM_CONDITION_ID`, not a rolled condition:
every one of those three systems is unconditionally registered for every
scene (see `scenes.py`), so an immediately-active random condition would
have quietly changed growth/evaporation/pest-spread timing for every
existing test and every ordinary game start, the moment this system was
added -- a coin flip nobody asked to make. Calm's own fields are
`WeatherCondition`'s neutral defaults, so starting on it is identical to
no weather system existing at all. Real weather only ever begins at the
first `CONDITION_DURATION` boundary, in `update()`.

Forecast, not surprise: `self.forecast` names the conditions coming up
next, `FORECAST_LENGTH` of them, so a HUD panel can tell the player "rain's
coming" before it arrives -- the PRD's whole reason for a forecast over an
outbreak-style ambush.

Advanced once a night by `systems/day_resolver.py`, last of all: the sky
that was overhead tonight is the one the player saw forecast yesterday,
and `advance_day()` rolls tomorrow's. Nothing turns mid-day, because
nothing grows or dries mid-day either.

Weather *is* saved (`persistence_schema.WeatherSnapshot`), unlike in the
real-time build where a fresh roll on load cost nothing. A condition now
lasts a whole day and the forecast is two days of planning, so re-rolling
it would quietly rewrite a decision the player had already made.
"""

from __future__ import annotations

from games.quintal_cerrado.weather import (
    CALM_CONDITION_ID,
    WEATHER_TABLE,
    WeatherState,
    roll_condition,
)
from pyguara.common.random import RandomStream

CONDITION_DURATION = 1.0
"""Days one condition lasts: exactly one. The garden is turn-based, and a
sky that changed in the middle of a day would change nothing, since nothing
grows or dries until the night resolves it. Kept as a named constant
because it is what makes `forecast` mean "the next two days"."""

FORECAST_LENGTH = 2
"""How many days ahead `forecast` names."""


class WeatherSystem:
    """Advances the current condition on a timer, and refills the forecast."""

    def __init__(
        self,
        state: WeatherState | None = None,
        rng: RandomStream | None = None,
        forecast_length: int = FORECAST_LENGTH,
    ) -> None:
        """Initialize the system, and roll a starting condition + forecast.

        Args:
            state: The `WeatherState` to overwrite each condition change.
                Pass the same instance `SoilSystem`/`PestSystem`/
                `PlantGrowthSystem` were given, so they see this system's
                writes. Defaults to a fresh, unshared one (mostly for
                tests that only care about this system in isolation).
            rng: Rolls both the starting queue and every condition after
                it. Pass a seeded stream for a reproducible one.
            forecast_length: How many upcoming conditions to keep queued.
        """
        self.state = state if state is not None else WeatherState()
        self._rng = rng if rng is not None else RandomStream()
        # Starts on CALM_CONDITION_ID deliberately, not a roll -- see the
        # module docstring's second paragraph. Only the *forecast* is
        # rolled up front; the active condition only ever changes at a
        # CONDITION_DURATION boundary, in `update()`.
        self._queue = [roll_condition(self._rng) for _ in range(forecast_length)]
        self._apply(CALM_CONDITION_ID)

    @property
    def forecast(self) -> list[str]:
        """The upcoming `condition_id`s, nearest first."""
        return list(self._queue)

    def restore(self, condition_id: str, forecast: list[str]) -> None:
        """Put back a saved sky, instead of the one this system rolled.

        A condition lasts a whole day now, so re-rolling on load would
        quietly rewrite the forecast the player planned around.

        Args:
            condition_id: The condition to put back in force.
            forecast: The upcoming conditions, nearest first.
        """
        if forecast:
            self._queue = list(forecast)
        self._apply(condition_id)

    def advance_day(self) -> None:
        """Move to tomorrow's condition and queue one more behind it.

        Called once a night by `systems/day_resolver.py`. There is no timer
        any more: a condition lasts a day because a day is the unit.
        """
        self._queue.append(roll_condition(self._rng))
        self._apply(self._queue.pop(0))

    def _apply(self, condition_id: str) -> None:
        condition = WEATHER_TABLE[condition_id]
        self.state.condition_id = condition_id
        self.state.growth_multiplier = condition.growth_multiplier
        self.state.moisture_gain_per_day = condition.moisture_gain_per_day
        self.state.evaporation_multiplier = condition.evaporation_multiplier
        self.state.pest_spread_multiplier = condition.pest_spread_multiplier
        self.state.cold_snap = condition.cold_snap
