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

Registered *after* `PlantGrowthSystem`/`WeedSpreadSystem` (see
`scenes.py`), not before, even though its `WeatherState` feeds systems
that run earlier in the same tick -- game systems cannot register below
priority 500, where `SoilSystem` already sits. The state a condition
change writes here is read by everything else one tick later, the same
one-frame lag `plant_growth_system.py`'s own docstring already accepts
for a stage transition; at 60Hz it is imperceptible.

Weather state is not saved: like `WeedSpreadSystem`'s check timer, a
loaded garden simply rolls a fresh condition and forecast from the load
moment, rather than round-tripping through the save schema for a value
a few seconds of play makes irrelevant again anyway.
"""

from __future__ import annotations

from games.quintal_cerrado.weather import (
    CALM_CONDITION_ID,
    WEATHER_TABLE,
    WeatherState,
    roll_condition,
)
from pyguara.common.random import RandomStream

CONDITION_DURATION = 90.0
"""Seconds one condition lasts. A 900s (15-minute) session sees roughly
ten changes -- "a few hours ahead" reads as true without being so frequent
it feels arbitrary."""

FORECAST_LENGTH = 2
"""How many conditions ahead `forecast` names."""


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
        self._timer = 0.0
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

    @property
    def condition_progress(self) -> float:
        """How far the current condition has run, 0.0 to 1.0.

        What the HUD's weather card fills its bar from, so "how long is
        this rain going to last" is answerable without counting seconds.
        """
        return min(1.0, self._timer / CONDITION_DURATION)

    def update(self, dt: float) -> None:
        """Advance the clock, and change condition once it comes due."""
        self._timer += dt
        if self._timer < CONDITION_DURATION:
            return
        self._timer -= CONDITION_DURATION
        self._queue.append(roll_condition(self._rng))
        self._apply(self._queue.pop(0))

    def _apply(self, condition_id: str) -> None:
        condition = WEATHER_TABLE[condition_id]
        self.state.condition_id = condition_id
        self.state.growth_multiplier = condition.growth_multiplier
        self.state.moisture_gain_per_second = condition.moisture_gain_per_second
        self.state.evaporation_multiplier = condition.evaporation_multiplier
        self.state.pest_spread_multiplier = condition.pest_spread_multiplier
        self.state.cold_snap = condition.cold_snap
