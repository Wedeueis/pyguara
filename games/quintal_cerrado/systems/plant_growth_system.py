"""Accumulates every planted entity's growth progress, every tick.

Reads `PlantComponent.growth_multiplier`, which `syntropic_system.py` must
have already written this tick (see the priority constants in
`scenes.py`), each species' `stage_seconds` from `species.py`, and the
cell's own `SoilCell.moisture` -- growth stalls below
`MOISTURE_GROWTH_THRESHOLD` rather than merely slowing, so watering is a
real, revisit-worthy action and not flavour text on a number nothing
reads. `systems/soil_system.py` is what makes that threshold something a
player crosses again over time rather than only once.

The engine's own `AISystem` (priority 200, auto-registered by every
`Scene`) is what actually reads the accumulated `growth_progress` and
transitions a stage -- see `plant_states.py`. Game systems register at
`GAME_SYSTEM_PRIORITY_MIN` (500) or above (`pyguara/scene/base.py`), so
this system's update always lands *after* `AISystem`'s for the same tick:
a stage transition is one frame behind the progress that triggered it. At
60Hz that is a single, imperceptible frame, not a bug to chase.
"""

from __future__ import annotations

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.species import SPECIES_TABLE
from pyguara.ecs.manager import EntityManager

MOISTURE_GROWTH_THRESHOLD = 0.15
"""Below this, a plant's growth simply does not advance this tick."""


class PlantGrowthSystem:
    """Advances every planted entity's `growth_progress`."""

    def __init__(self, entity_manager: EntityManager, grid: GardenGrid) -> None:
        """Initialize the system.

        Args:
            entity_manager: Where planted entities live.
            grid: The plot whose `plant_at` occupancy and soil this system
                reads.
        """
        self._entity_manager = entity_manager
        self._grid = grid

    def update(self, dt: float) -> None:
        """Advance every planted entity's `growth_progress` by one tick."""
        for cell, entity_id in self._grid.plant_at.items():
            entity = self._entity_manager.get_entity(entity_id)
            if entity is None or not entity.has_component(PlantComponent):
                continue
            plant = entity.get_component(PlantComponent)
            if plant.growth_stage == "harvestable":
                # Terminal for now (selling is Phase 3's economy system)
                # -- stop accumulating rather than let an unbounded number
                # sit in a field the save schema will read.
                continue
            if self._grid.soil_at(cell).moisture < MOISTURE_GROWTH_THRESHOLD:
                continue
            species = SPECIES_TABLE.get(plant.species_id)
            if species is None or species.stage_seconds <= 0:
                continue
            plant.growth_progress += (
                dt / species.stage_seconds
            ) * plant.growth_multiplier
