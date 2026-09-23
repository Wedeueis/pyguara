"""The plot acting on its own: weeds spring up, and grown plants self-seed.

One system for both, because they are the same mechanic at different
rates. A mature-or-later plant (`SPREADING_STAGES`) has a chance, each
night, to seed a free neighbouring tilled cell with a plant of its own
species -- `Species.spread_chance` is the *only* thing that tells a weed's
aggressive colonisation from a baru tree's occasional self-seed apart, the
same way `Species.repels_pests` is the only thing that singles out Pequi in
`pest_system.py`. There is no `if species_id == "weed"` branch in the
spreading logic at all. Weeds additionally get a small chance to spring up
from nothing on any bare tilled cell -- real weeds don't need a parent
plant nearby.

Once a night, from `systems/day_resolver.py`, and after the growth pass, so
a plant that matured tonight is eligible tonight rather than a day later.
There is no timer left to persist: a night either happened or it did not.
"""

from __future__ import annotations

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.plant_states import build_plant_ai
from games.quintal_cerrado.species import SPECIES_TABLE, WEED_SPECIES_ID
from pyguara.common.grid import Cell, neighbors8
from pyguara.common.random import RandomStream
from pyguara.ecs.manager import EntityManager

SPONTANEOUS_WEED_CHANCE = 0.25
"""Chance, per night, that *some* empty tilled cell on the whole plot
sprouts a weed on its own. A quarter a night means an unweeded plot has one
within its first few days without every morning bringing a chore."""

SPREADING_STAGES = frozenset({"mature", "harvestable", "overripe"})
"""A plant this young or this sick does not spread: `"growing"` hasn't
finished proving itself, and `"infested"`/`"dying"` have nothing to spare."""


class WeedSpreadSystem:
    """Rolls every grown plant's spread chance, and weeds' spontaneous one."""

    def __init__(
        self,
        entity_manager: EntityManager,
        grid: GardenGrid,
        rng: RandomStream | None = None,
    ) -> None:
        """Initialize the system.

        Args:
            entity_manager: Where planted entities live, and where a
                spread or a spontaneous weed is created.
            grid: The plot.
            rng: Picks which cell a spread lands on, and rolls every
                chance. Pass a seeded stream for a reproducible one.
        """
        self._entity_manager = entity_manager
        self._grid = grid
        self._rng = rng if rng is not None else RandomStream()

    def resolve_night(self) -> None:
        """One spread roll per eligible plant, and one spontaneous weed roll.

        Once a night, not on a timer: a weed taking new ground is the kind
        of thing that should have happened *while you slept*, not under the
        cursor while you were deciding where to plant.
        """
        self._spread_existing()
        self._spawn_spontaneous_weed()

    def _spread_existing(self) -> None:
        """One roll per eligible plant, against the plot as it stood at
        nightfall -- a weed created tonight must not itself spread tonight."""
        for cell, entity_id in list(self._grid.plant_at.items()):
            entity = self._entity_manager.get_entity(entity_id)
            if entity is None or not entity.has_component(PlantComponent):
                continue
            plant = entity.get_component(PlantComponent)
            if plant.growth_stage not in SPREADING_STAGES:
                continue
            species = SPECIES_TABLE.get(plant.species_id)
            if species is None or species.spread_chance <= 0.0:
                continue
            if self._rng.random() >= species.spread_chance:
                continue
            self._plant_on_a_free_neighbor(cell, plant.species_id)

    def _spawn_spontaneous_weed(self) -> None:
        empty_tilled = [
            (x, y)
            for y, row in enumerate(self._grid.soil)
            for x, soil in enumerate(row)
            if soil.soil_type == "tilled_dirt" and self._grid.can_plant((x, y))
        ]
        if not empty_tilled or self._rng.random() >= SPONTANEOUS_WEED_CHANCE:
            return
        self._plant(self._rng.choice(empty_tilled), WEED_SPECIES_ID)

    def _plant_on_a_free_neighbor(self, source: Cell, species_id: str) -> None:
        targets = [
            neighbor
            for neighbor in neighbors8(source)
            if self._grid.can_plant(neighbor)
        ]
        if not targets:
            return
        self._plant(self._rng.choice(targets), species_id)

    def _plant(self, cell: Cell, species_id: str) -> None:
        entity = self._entity_manager.create_entity()
        entity.add_component(PlantComponent(species_id=species_id))
        entity.add_component(build_plant_ai(entity))
        self._grid.mark_planted(cell, entity.id)
