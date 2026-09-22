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

CHEMICAL_GROWTH_BOOST = 1.5
"""The chemical shortcut's "fast yield boost" (PRD): a plant that was ever
sprayed grows this much faster -- and sells for half, see `economy.py`."""

DEGRADED_SOIL_GROWTH = 0.8
"""Growth multiplier on chemically degraded soil, the cost the PRD says the
shortcut leaves in the ground."""

FROZEN_STAGES = frozenset({"overripe", "infested", "dying"})
"""Stages that do not accumulate growth. `"harvestable"` is deliberately
*not* frozen: `plant_states.HarvestableState` reuses this same
`growth_progress` accumulation as its ripeness clock, reading it against
`OVERRIPE_THRESHOLD` to decide when to go `"overripe"` -- which then is
frozen, the same as an infested or dying plant that is done changing."""


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
            if plant.growth_stage in FROZEN_STAGES:
                # Stop accumulating rather than let an unbounded number sit
                # in a field the save schema will read.
                continue
            soil = self._grid.soil_at(cell)
            if soil.moisture < MOISTURE_GROWTH_THRESHOLD:
                continue
            species = SPECIES_TABLE.get(plant.species_id)
            if species is None or species.stage_seconds <= 0:
                continue
            multiplier = plant.growth_multiplier
            if plant.is_chemical_boosted:
                multiplier *= CHEMICAL_GROWTH_BOOST
            if soil.is_chemically_degraded:
                multiplier *= DEGRADED_SOIL_GROWTH
            plant.growth_progress += (dt / species.stage_seconds) * multiplier
