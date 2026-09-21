"""Recomputes each cell's `shade_level` from grown canopy-layer plants.

Reset-then-accumulate every tick rather than incremental bookkeeping -- a
plant's growth stage changes, and the whole plot is 96 cells, cheap enough
to recompute outright rather than track deltas.

Must run before `syntropic_system.py`: an understory plant's companion
bonus reads the `shade_level` this system just wrote (see the priority
constants in `scenes.py`).
"""

from __future__ import annotations

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.species import SPECIES_TABLE
from pyguara.common.grid import Cell, neighbors8
from pyguara.ecs.manager import EntityManager

OWN_CELL_SHADE = 0.4
"""Shade a grown canopy plant casts on its own cell."""

NEIGHBOR_SHADE = 0.25
"""Shade cast on each of the 8 neighbouring cells."""

SHADE_CASTING_STAGES = frozenset({"mature", "harvestable"})
"""A seedling or growing canopy tree has no canopy yet to cast shade with."""


class ShadeSystem:
    """Casts shade from grown canopy-layer plants onto their neighbours."""

    def __init__(self, entity_manager: EntityManager, grid: GardenGrid) -> None:
        """Initialize the system.

        Args:
            entity_manager: Where planted entities live.
            grid: The plot whose `SoilCell.shade_level` this system writes.
        """
        self._entity_manager = entity_manager
        self._grid = grid

    def update(self, dt: float) -> None:
        """Reset every cell's shade, then re-cast it from grown canopies."""
        for row in self._grid.soil:
            for soil in row:
                soil.shade_level = 0.0

        for cell, entity_id in self._grid.plant_at.items():
            entity = self._entity_manager.get_entity(entity_id)
            if entity is None or not entity.has_component(PlantComponent):
                continue
            plant = entity.get_component(PlantComponent)
            species = SPECIES_TABLE.get(plant.species_id)
            if species is None or species.canopy_layer != "canopy":
                continue
            if plant.growth_stage not in SHADE_CASTING_STAGES:
                continue

            self._add_shade(cell, OWN_CELL_SHADE)
            for neighbor in neighbors8(cell):
                self._add_shade(neighbor, NEIGHBOR_SHADE)

    def _add_shade(self, cell: Cell, amount: float) -> None:
        if not self._grid.in_bounds(cell):
            return
        soil = self._grid.soil_at(cell)
        soil.shade_level = min(1.0, soil.shade_level + amount)
