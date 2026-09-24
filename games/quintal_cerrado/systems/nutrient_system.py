"""What growing takes out of the soil, and what each plant puts back.

Every plant feeds while it grows -- more of it the bigger the plant
(`Species.appetite`) -- so a cell worked hard without care runs down, and
`nutrients.scarcest` starts naming what it is short of. That alone would
only be attrition. What makes it a system worth playing is that some
plants *give*:

- a legume (Guandu) fixes **nitrogen** into its own cell and the eight
  around it, which is why interplanting it beats growing it alone;
- a deep-rooted canopy tree (Baru) lifts **potassium** to the surface for
  everything beneath it;
- a grown Pequi leaves **calcium**, which is the same plant that already
  repels pests -- so the species that answers an outbreak is also the one
  that leaves the ground able to resist the next.

A plant only gives once it is grown: the payoff is for leaving something
standing, not for planting it and harvesting it immediately.

Compost is the other half (`treatments.py`): the player's way to put
nitrogen and phosphorus back without waiting for a consortium to do it.
"""

from __future__ import annotations

from games.quintal_cerrado import nutrients
from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.species import SPECIES_TABLE
from pyguara.common.grid import Cell, neighbors8
from pyguara.ecs.manager import EntityManager

UPTAKE = 0.06
"""Nitrogen and phosphorus a growing plant of appetite 1.0 takes a night."""

FIXING = 0.09
"""Nitrogen a legume adds to its own cell each night."""

NEIGHBOUR_SHARE = 0.5
"""How much of that reaches each of the eight cells around it -- the part
that makes interplanting a legume worth doing."""

LIFTING = 0.07
"""Potassium a deep-rooted tree brings up, for itself and its neighbours."""

LEAVING = 0.06
"""Calcium a grown Pequi leaves in its own cell and around it."""

GIVING_STAGES = frozenset({"mature", "harvestable", "overripe"})
"""A plant gives only once it is grown. A seedling is still taking."""

FEEDING_STAGES = frozenset({"seedling", "growing", "mature", "harvestable"})
"""Stages that draw on the soil. A dying or infested plant has stopped."""

CEILING = 1.0


class NutrientSystem:
    """Moves nutrients between the plants and the soil, once a night."""

    def __init__(self, entity_manager: EntityManager, grid: GardenGrid) -> None:
        """Bind the system to the plot.

        Args:
            entity_manager: Where the plants live.
            grid: The plot whose `SoilCell`s this feeds and drains.
        """
        self._entity_manager = entity_manager
        self._grid = grid

    def resolve_night(self) -> None:
        """Take what the plants ate, then add what the grown ones gave."""
        for cell, plant in self._plants():
            species = SPECIES_TABLE.get(plant.species_id)
            if species is None:
                continue
            if plant.growth_stage in FEEDING_STAGES:
                self._feed(cell, species.appetite)
            if plant.growth_stage in GIVING_STAGES:
                self._give(cell, species)

    def _plants(self) -> list[tuple[Cell, PlantComponent]]:
        """Every planted cell's `(cell, plant)`, as it stood at nightfall."""
        found = []
        for cell, entity_id in list(self._grid.plant_at.items()):
            entity = self._entity_manager.get_entity(entity_id)
            if entity is not None and entity.has_component(PlantComponent):
                found.append((cell, entity.get_component(PlantComponent)))
        return found

    def _feed(self, cell: Cell, appetite: float) -> None:
        """Draw this plant's night of nitrogen and phosphorus."""
        soil = self._grid.soil_at(cell)
        drawn = UPTAKE * appetite
        soil.nitrogen = max(0.0, soil.nitrogen - drawn)
        soil.phosphorus = max(0.0, soil.phosphorus - drawn)

    def _give(self, cell: Cell, species: object) -> None:
        """Add whatever a grown plant of this species puts back."""
        if getattr(species, "fixes_nitrogen", False):
            self._spread(cell, nutrients.NITROGEN, FIXING)
        if getattr(species, "lifts_potassium", False):
            self._spread(cell, nutrients.POTASSIUM, LIFTING)
        if getattr(species, "leaves_calcium", False):
            self._spread(cell, nutrients.CALCIUM, LEAVING)

    def _spread(self, cell: Cell, nutrient: str, amount: float) -> None:
        """Add `amount` here, and a share of it to each neighbour."""
        self._add(cell, nutrient, amount)
        for neighbour in neighbors8(cell):
            if self._grid.in_bounds(neighbour):
                self._add(neighbour, nutrient, amount * NEIGHBOUR_SHARE)

    def _add(self, cell: Cell, nutrient: str, amount: float) -> None:
        soil = self._grid.soil_at(cell)
        setattr(soil, nutrient, min(CEILING, getattr(soil, nutrient) + amount))
