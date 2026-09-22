"""Pest pressure: it spreads between plants, decays, and wears plants down.

Three forces, all per tick, all reading only the plot:

- **Spread.** A cell carrying real pressure passes some to each neighbouring
  cell that holds a vulnerable plant -- faster if the neighbour is the same
  species (a monoculture is a buffet), which is the flip side of the
  companion bonus in `syntropic_system.py`.
- **Decay.** Pressure falls in proportion to the cell's organic matter --
  this is what compost buys, slowly -- plus a flat extra where a grown
  Pequi is on or beside the cell (`Species.repels_pests`), the PRD's "pest
  resistance via flora" -- and a flat extra on any cell with no vulnerable
  plant, since pests with nothing to feed on die off. A chemical spray
  skips all of this and zeroes the cells outright (`components.spray_cell`).
- **Wear.** A vulnerable plant at or above `RECOVER_THRESHOLD` pressure --
  that is, for as long as it stays infested, not just while the pressure
  is at its worst -- loses health; below it, the plant slowly regains it.
  Left alone, a single infested plant dies in about twenty-five seconds,
  which is what makes ignoring an outbreak a losing move. `plant_states.py`
  moves the plant to `infested`/`dying` from these numbers -- this system
  never changes a plant's stage itself.

Seedlings are immune: a plant that can lose health but has no `dying`
state to reach would sit at zero health forever.

Registered between `SyntropicSystem` and `PlantGrowthSystem` (see
`scenes.py`); the engine's own `AISystem` reads the plant's mirrored
`pest_pressure` on the following tick.
"""

from __future__ import annotations

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.plant_states import RECOVER_THRESHOLD
from games.quintal_cerrado.species import SPECIES_TABLE
from games.quintal_cerrado.weather import WeatherState
from pyguara.common.grid import Cell, neighbors8
from pyguara.ecs.manager import EntityManager

SPREAD_RATE = 0.04
"""Fraction of a source cell's pressure each neighbouring plant receives per
second."""

SPREAD_MIN_PRESSURE = 0.3
"""Below this a cell is too mild to pass anything on."""

MONOCULTURE_SPREAD = 1.5
"""Spread multiplier when source and target plants are the same species."""

ORGANIC_DECAY = 0.06
"""Pressure lost per second per unit of organic matter."""

PEQUI_DECAY = 0.04
"""Extra pressure lost per second where a grown Pequi is on or beside a cell."""

NO_HOST_DECAY = 0.05
"""Extra pressure lost per second on a cell with no vulnerable plant: pests
with nothing to feed on die off, so a cleared field stops being an outbreak."""

HEALTH_DRAIN = 0.08
"""Health an infested plant loses per second, per unit of pressure."""

HEALTH_REGEN = 0.02
"""Health a plant under `RECOVER_THRESHOLD` pressure regains per second."""

VULNERABLE_STAGES = frozenset(
    {"growing", "mature", "harvestable", "overripe", "infested"}
)
"""Stages pests can reach. Seedlings are immune, and a dying plant has
nothing left to lose. `"overripe"` counts too -- otherwise leaving a plant
past its ripe window would be a free way to dodge an outbreak."""

_GROWN_STAGES = frozenset({"mature", "harvestable", "overripe"})
_SNAP_TO_ZERO = 0.02


class PestSystem:
    """Spreads, decays and applies pest pressure across the plot."""

    def __init__(
        self,
        entity_manager: EntityManager,
        grid: GardenGrid,
        weather: WeatherState | None = None,
    ) -> None:
        """Initialize the system.

        Args:
            entity_manager: Where planted entities live.
            grid: The plot whose `SoilCell.pest_pressure` this system owns.
            weather: The live weather, if any -- wind's spread multiplier
                applies on top of `SPREAD_RATE`. `None` behaves as calm.
        """
        self._entity_manager = entity_manager
        self._grid = grid
        self._weather = weather

    def update(self, dt: float) -> None:
        """Move pressure around the plot, then apply it to the plants."""
        self._update_pressure(dt)
        self._update_plants(dt)

    def _plant_at(self, cell: Cell) -> PlantComponent | None:
        entity_id = self._grid.plant_at.get(cell)
        if entity_id is None:
            return None
        entity = self._entity_manager.get_entity(entity_id)
        if entity is None or not entity.has_component(PlantComponent):
            return None
        return entity.get_component(PlantComponent)

    def _is_repelled(self, cell: Cell) -> bool:
        """Whether a grown pest-repelling plant is on or beside `cell`."""
        for candidate in (cell, *neighbors8(cell)):
            plant = self._plant_at(candidate)
            if plant is None or plant.growth_stage not in _GROWN_STAGES:
                continue
            species = SPECIES_TABLE.get(plant.species_id)
            if species is not None and species.repels_pests:
                return True
        return False

    def _update_pressure(self, dt: float) -> None:
        deltas: dict[Cell, float] = {}
        spread_rate = SPREAD_RATE * (
            self._weather.pest_spread_multiplier if self._weather else 1.0
        )

        for y, row in enumerate(self._grid.soil):
            for x, soil in enumerate(row):
                pressure = soil.pest_pressure
                if pressure <= 0.0:
                    continue
                cell = (x, y)

                decay = soil.organic_matter * ORGANIC_DECAY
                if self._is_repelled(cell):
                    decay += PEQUI_DECAY
                host = self._plant_at(cell)
                if host is None or host.growth_stage not in VULNERABLE_STAGES:
                    decay += NO_HOST_DECAY
                deltas[cell] = deltas.get(cell, 0.0) - decay * dt

                if pressure < SPREAD_MIN_PRESSURE:
                    continue
                source = self._plant_at(cell)
                for neighbor in neighbors8(cell):
                    if not self._grid.in_bounds(neighbor):
                        continue
                    target = self._plant_at(neighbor)
                    if target is None or target.growth_stage not in VULNERABLE_STAGES:
                        continue
                    rate = spread_rate
                    if source is not None and source.species_id == target.species_id:
                        rate *= MONOCULTURE_SPREAD
                    deltas[neighbor] = deltas.get(neighbor, 0.0) + rate * pressure * dt

        for cell, delta in deltas.items():
            soil = self._grid.soil_at(cell)
            updated = min(1.0, max(0.0, soil.pest_pressure + delta))
            # Snap a fading cell to exactly zero so an outbreak can end, but
            # only if it is net-fading: spread deposits a fraction of a
            # percent per tick, and snapping *that* would zero a cell before
            # it could ever accumulate anything.
            if delta < 0.0 and updated < _SNAP_TO_ZERO:
                updated = 0.0
            soil.pest_pressure = updated

    def _update_plants(self, dt: float) -> None:
        for cell in self._grid.plant_at:
            plant = self._plant_at(cell)
            if plant is None:
                continue
            pressure = self._grid.soil_at(cell).pest_pressure
            plant.pest_pressure = pressure
            if plant.growth_stage not in VULNERABLE_STAGES:
                continue
            if pressure >= RECOVER_THRESHOLD:
                plant.health = max(0.0, plant.health - HEALTH_DRAIN * pressure * dt)
            else:
                plant.health = min(1.0, plant.health + HEALTH_REGEN * dt)
