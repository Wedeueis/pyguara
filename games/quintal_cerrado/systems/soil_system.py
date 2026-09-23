"""Evaporates soil moisture every tick, and lets rain top it back up.

Registered before `shade_system.py`/`plant_growth_system.py` in the
priority order (see `scenes.py`). Shade and the companion bonus don't
read moisture, but `plant_growth_system.py` does -- this is what makes
watering something a player has to keep doing, not a one-time click.
Weather (`weather.py`) only ever adjusts the two numbers below -- how
fast evaporation runs, and how much rain adds -- moisture itself stays
this system's alone to own and mutate.
"""

from __future__ import annotations

from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.weather import WeatherState

EVAPORATION_RATE = 0.05
"""Moisture a cell loses per simulated second at multiplier 1.0.

Retuned for the turn-based build: a night is `day_resolver.DAY_SIM_SECONDS`
of this, so a watering (`components.WATER_AMOUNT`, 0.4) carries a cell about
two and a half days. At the old rate it lasted over a week, and watering
stopped being a decision."""


class SoilSystem:
    """Dries out every cell's soil a little, every tick -- and wets it
    back down where rain is currently falling."""

    def __init__(self, grid: GardenGrid, weather: WeatherState | None = None) -> None:
        """Initialize the system.

        Args:
            grid: The plot whose `SoilCell.moisture` this system decays.
            weather: The live weather, if any -- its evaporation
                multiplier and rain rate apply on top of the base
                numbers above. `None` (a test with no weather system
                registered) behaves exactly as if the weather were
                always calm and dry.
        """
        self._grid = grid
        self._weather = weather

    def update(self, dt: float) -> None:
        """Rain a tilled cell up, then evaporate every cell back down."""
        rain = self._weather.moisture_gain_per_second if self._weather else 0.0
        evaporation = EVAPORATION_RATE * (
            self._weather.evaporation_multiplier if self._weather else 1.0
        )
        for row in self._grid.soil:
            for soil in row:
                if rain > 0.0 and soil.soil_type == "tilled_dirt":
                    soil.moisture = min(1.0, soil.moisture + rain * dt)
                if soil.moisture > 0.0:
                    soil.moisture = max(0.0, soil.moisture - evaporation * dt)
