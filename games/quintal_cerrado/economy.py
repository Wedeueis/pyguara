"""Prices, and the organic-versus-chemical fork in what a harvest sells for.

The PRD's dilemma in one place: a plant that was ever chemically treated
sells at half the market rate, and one that never was sells at double it.
That is the whole reason the natural path is worth its slower recovery --
`treatments.py`'s spray fixes a pest outbreak instantly and costs the
premium for good, since `PlantComponent.is_chemical_boosted` never clears.

A set of free functions rather than a ticking `economy_system.py`: unlike
soil or shade, nothing about money changes on its own between player
actions, so there is nothing for a system to tick.

`harvest_cell()` is the one place a harvest becomes value -- Sementes, or
a seed -- shared by the player's own harvest tool and a harvester drone,
the same way `sell_harvest` alone used to be before the fun-improvement
roadmap's Phase 3 gave a harvest three possible outcomes instead of one:
a crop collected at its peak still sells for Sementes; a weed, or a crop
left to go `"overripe"`, pays out in seed stock instead (`components.py`'s
`grant_seed`) -- generic for a weed, specific to its own species for an
overripe crop.
"""

from __future__ import annotations

from dataclasses import dataclass

from games.quintal_cerrado import nutrients
from games.quintal_cerrado.components import (
    GENERIC_SEED_KEY,
    PlantComponent,
    PlayerEconomy,
    SoilCell,
    add_credits,
    grant_seed,
    specific_seed_key,
)
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.species import SPECIES_TABLE, WEED_SPECIES_ID
from pyguara.common.grid import Cell
from pyguara.ecs.manager import EntityManager

COMPOST_COST = 5
SPRAY_COST = 25

ORGANIC_PREMIUM = 2.0
"""Sale multiplier for a plant never touched by chemicals (PRD: 2.0x)."""

CHEMICAL_DISCOUNT = 0.5
"""Sale multiplier for a chemically treated plant (PRD: 0.5x)."""


def sale_multiplier(plant: PlantComponent) -> float:
    """How much of the market rate `plant` fetches.

    Args:
        plant: The plant being sold.

    Returns:
        `CHEMICAL_DISCOUNT` if it was ever sprayed, else `ORGANIC_PREMIUM`.
    """
    return CHEMICAL_DISCOUNT if plant.is_chemical_boosted else ORGANIC_PREMIUM


def sale_value(plant: PlantComponent, soil: SoilCell | None = None) -> int:
    """Whole Sementes `plant` sells for.

    Args:
        plant: The plant being sold.
        soil: The cell it grew in, whose phosphorus adds to the price --
            the one thing that nutrient governs. None ignores the soil,
            which is what a caller with only a plant in hand wants.

    Returns:
        Its species' base price times `sale_multiplier`, rounded to a whole
        number and never less than 1 -- an unknown species sells for 0.
    """
    species = SPECIES_TABLE.get(plant.species_id)
    if species is None:
        return 0
    value = species.base_price * sale_multiplier(plant)
    if soil is not None:
        value *= nutrients.value_multiplier(soil)
    return max(1, round(value))


CREDITS = "credits"
GENERIC_SEED = "generic_seed"
SPECIFIC_SEED = "specific_seed"
"""The three ways `harvest_cell` can pay out -- `HarvestResult.kind`."""

OVERRIPE_WEED_SEED_BONUS = 2
"""Generic seed a weed pays out if pulled `"overripe"` rather than
`"harvestable"` -- letting one go to seed on purpose is worth more than
yanking it young, the same trade-off overripening gives a real crop."""

READY_STAGES = frozenset({"harvestable", "overripe"})


@dataclass(frozen=True)
class HarvestResult:
    """What harvesting one cell produced.

    Attributes:
        species_id: What was harvested.
        kind: `CREDITS`, `GENERIC_SEED` or `SPECIFIC_SEED`.
        amount: Sementes for `CREDITS`, a seed count for either seed kind.
    """

    species_id: str
    kind: str
    amount: int


def harvest_cell(
    grid: GardenGrid,
    entity_manager: EntityManager,
    economy: PlayerEconomy,
    cell: Cell,
) -> HarvestResult | None:
    """Collect whatever `cell` is ready to give up, freeing the (still
    tilled) cell either way.

    The one place a harvest becomes value -- see the module docstring for
    the three outcomes -- shared by the player's own harvest tool and a
    harvester drone, so the two cannot disagree on what a plant is worth.

    Args:
        grid: The plot.
        entity_manager: Where the plant lives.
        economy: Who is paid, or whose seed stock grows.
        cell: The cell to harvest.

    Returns:
        The `HarvestResult`, or None -- nothing there, not ready yet, or
        infested.
    """
    entity_id = grid.plant_at.get(cell)
    if entity_id is None:
        return None
    entity = entity_manager.get_entity(entity_id)
    if entity is None or not entity.has_component(PlantComponent):
        return None
    plant = entity.get_component(PlantComponent)
    if plant.growth_stage not in READY_STAGES:
        return None

    species_id = plant.species_id
    is_overripe = plant.growth_stage == "overripe"

    if species_id == WEED_SPECIES_ID:
        amount = OVERRIPE_WEED_SEED_BONUS if is_overripe else 1
        grant_seed(economy, GENERIC_SEED_KEY, amount)
        result = HarvestResult(species_id, GENERIC_SEED, amount)
    elif is_overripe:
        grant_seed(economy, specific_seed_key(species_id), 1)
        result = HarvestResult(species_id, SPECIFIC_SEED, 1)
    else:
        value = sale_value(plant, grid.soil_at(cell))
        add_credits(economy, value)
        if plant.is_chemical_boosted:
            economy.chemical_sales += 1
        else:
            economy.organic_sales += 1
        result = HarvestResult(species_id, CREDITS, value)

    entity_manager.remove_entity(entity_id)
    grid.unmark_planted(cell)
    return result
