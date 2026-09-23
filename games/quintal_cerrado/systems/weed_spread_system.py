"""The plot acting on its own: weeds spring up, and grown plants self-seed.

One system for both, because they are the same mechanic at different
rates. A mature-or-later plant (`SPREADING_STAGES`) has a chance, each
time this system checks, to seed a free neighbouring tilled cell with a
plant of its own species -- `Species.spread_chance` is the *only* thing
that tells a weed's aggressive colonisation from a baru tree's occasional
self-seed apart, the same way `Species.repels_pests` is the only thing
that singles out Pequi in `pest_system.py`. There is no
`if species_id == "weed"` branch in the spreading logic at all. Weeds
additionally get a small chance to spring up from nothing on any bare
tilled cell each check -- real weeds don't need a parent plant nearby.

Checked every `PROPAGATION_INTERVAL` seconds rather than every tick, on
purpose: a probability meant to read as "rare over a 15-minute session"
or "fast, but not instant" needs a coarse enough clock that a handful of
ticks (most of this game's own tests) never reaches even one check. A
per-tick roll would make the exact same odds fire dozens of times a
second, and either wash out into nothing at those odds or need numbers
too small to reason about.

Registered after `PlantGrowthSystem` (see `scenes.py`) so a plant that
became mature this tick is eligible on the very next check, not a whole
system-ordering cycle later. `self._timer` is not persisted -- a loaded
garden's next check simply starts counting from the load moment, the one
piece of this system's state a save does not carry, since it belongs to
no entity or component the schema already round-trips.
"""

from __future__ import annotations

from games.quintal_cerrado.components import PlantComponent
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.plant_states import build_plant_ai
from games.quintal_cerrado.species import SPECIES_TABLE, WEED_SPECIES_ID
from pyguara.common.grid import Cell, neighbors8
from pyguara.common.random import RandomStream
from pyguara.ecs.manager import EntityManager

PROPAGATION_INTERVAL = 3.0
"""Simulated seconds between spread checks -- one night's worth
(`day_resolver.DAY_SIM_SECONDS`), so a weed gets exactly one chance to take
new ground per day and the plot never changes while you are looking at it."""

SPONTANEOUS_WEED_CHANCE = 0.06
"""Chance, per check, that *some* empty tilled cell on the whole plot
sprouts a weed on its own -- low, but enough that an unweeded plot
reliably grows one within its first few checks."""

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
        self._timer = 0.0

    def update(self, dt: float) -> None:
        """Advance the check clock, and run one check if it has come due."""
        self._timer += dt
        if self._timer < PROPAGATION_INTERVAL:
            return
        self._timer -= PROPAGATION_INTERVAL
        self._spread_existing()
        self._spawn_spontaneous_weed()

    def _spread_existing(self) -> None:
        """One spread roll per eligible plant, on the plot as it stood at
        the start of this check -- a spread created mid-check must not
        itself be rolled again before the next one."""
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
