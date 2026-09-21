"""Companion-planting growth bonus: the PRD's stratification consortium.

Ground-cover legumes (Guandu) fix nitrogen regardless of what grows beside
them, so any neighbour of a *different* canopy layer counts as a
companion -- "complementary species in adjacent cells" per the PRD, not
merely any neighbour at all (another Guandu beside a Guandu is not a
consortium). An understory plant's bonus specifically requires standing in
an already-grown canopy neighbour's shade (`shade_system.py` must run
first -- see the priority constants in `scenes.py`), matching the PRD's
own example -- "Cagaita under the shade of Baru" -- rather than bare
adjacency. A canopy plant is the top of the stack and has nothing above it
to benefit from.
"""

from __future__ import annotations

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.species import SPECIES_TABLE
from pyguara.common.grid import Cell, neighbors8
from pyguara.ecs.manager import EntityManager

COMPANION_GROWTH_MULTIPLIER = 1.4
"""The PRD's own figure: "boosts growth speed by 40%"."""

SHADE_BENEFIT_THRESHOLD = 0.2
"""Minimum `SoilCell.shade_level` an understory plant needs to count as
"in the shade" rather than merely near a canopy tree that isn't casting
much yet."""


class SyntropicSystem:
    """Sets each plant's `growth_multiplier` from its stratification."""

    def __init__(self, entity_manager: EntityManager, grid: GardenGrid) -> None:
        """Initialize the system.

        Args:
            entity_manager: Where planted entities live.
            grid: The plot whose occupancy and shade this system reads.
        """
        self._entity_manager = entity_manager
        self._grid = grid

    def update(self, dt: float) -> None:
        """Recompute every planted entity's `growth_multiplier`."""
        for cell, entity_id in self._grid.plant_at.items():
            entity = self._entity_manager.get_entity(entity_id)
            if entity is None or not entity.has_component(PlantComponent):
                continue
            plant = entity.get_component(PlantComponent)
            species = SPECIES_TABLE.get(plant.species_id)
            if species is None:
                continue
            plant.growth_multiplier = self._multiplier_for(cell, species.canopy_layer)

    def _multiplier_for(self, cell: Cell, canopy_layer: str) -> float:
        if canopy_layer == "canopy":
            return 1.0
        if canopy_layer == "understory":
            soil = self._grid.soil_at(cell) if self._grid.in_bounds(cell) else None
            shaded = soil is not None and soil.shade_level >= SHADE_BENEFIT_THRESHOLD
            return COMPANION_GROWTH_MULTIPLIER if shaded else 1.0
        # ground_cover, and any future layer: a differently-layered
        # neighbour is a companion.
        has_companion = self._has_different_layer_neighbor(cell, canopy_layer)
        return COMPANION_GROWTH_MULTIPLIER if has_companion else 1.0

    def _has_different_layer_neighbor(self, cell: Cell, own_layer: str) -> bool:
        for neighbor_cell in neighbors8(cell):
            if not self._grid.in_bounds(neighbor_cell):
                continue
            neighbor_id = self._grid.plant_at.get(neighbor_cell)
            if neighbor_id is None:
                continue
            neighbor = self._entity_manager.get_entity(neighbor_id)
            if neighbor is None or not neighbor.has_component(PlantComponent):
                continue
            neighbor_species = SPECIES_TABLE.get(
                neighbor.get_component(PlantComponent).species_id
            )
            if (
                neighbor_species is not None
                and neighbor_species.canopy_layer != own_layer
            ):
                return True
        return False
