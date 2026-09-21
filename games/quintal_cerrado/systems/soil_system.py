"""Evaporates soil moisture every tick.

Registered before `shade_system.py`/`plant_growth_system.py` in the
priority order (see `scenes.py`). Shade and the companion bonus don't
read moisture, but `plant_growth_system.py` does -- this is what makes
watering something a player has to keep doing, not a one-time click.
"""

from __future__ import annotations

from games.quintal_cerrado.garden_grid import GardenGrid

EVAPORATION_RATE = 0.015
"""Moisture lost per second. A single watering (+0.4, see
`components.WATER_AMOUNT`) buys roughly 0.4 / EVAPORATION_RATE =~ 27
seconds above zero -- long enough to outlast Guandu's whole lifecycle,
short enough that Baru's slower one needs a second pass."""


class SoilSystem:
    """Dries out every cell's soil a little, every tick."""

    def __init__(self, grid: GardenGrid) -> None:
        """Initialize the system.

        Args:
            grid: The plot whose `SoilCell.moisture` this system decays.
        """
        self._grid = grid

    def update(self, dt: float) -> None:
        """Decay every cell's moisture towards zero."""
        for row in self._grid.soil:
            for soil in row:
                if soil.moisture > 0.0:
                    soil.moisture = max(0.0, soil.moisture - EVAPORATION_RATE * dt)
