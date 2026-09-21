"""The player's two answers to a pest outbreak: compost, or spray.

The fork the PRD calls "The Agroecological Dilemma". Both cost Sementes.
Compost is slow and organic: it only raises organic matter, which
`systems/pest_system.py` turns into a faster pest decay, and it heals
chemical damage once the soil is rich enough. A spray is instant and
chemical: it clears pests on the cell and all eight around it, degrades
that soil, and permanently marks every plant it reaches as chemically
boosted -- which is what `economy.sale_value()` charges the premium for.
"""

from __future__ import annotations

from games.quintal_cerrado.components import (
    GardenConditions,
    PlantComponent,
    PlayerEconomy,
    compost_cell,
    spend_credits,
    spray_cell,
)
from games.quintal_cerrado.economy import COMPOST_COST, SPRAY_COST
from games.quintal_cerrado.garden_grid import GardenGrid
from pyguara.common.grid import Cell, neighbors8
from pyguara.ecs.manager import EntityManager

OK = "ok"
NOTHING = "nothing"
BROKE = "broke"
"""The three ways a treatment can end. `NOTHING` charges nothing: the cell
was out of bounds or already as rich as compost can make it."""


def apply_compost(
    grid: GardenGrid,
    economy: PlayerEconomy,
    conditions: GardenConditions,
    cell: Cell,
) -> str:
    """Compost `cell`, if it is tilled, not already saturated, and affordable.

    Args:
        grid: The plot.
        economy: Who pays.
        conditions: Records the answer as organic.
        cell: The cell to compost.

    Returns:
        `OK`, `NOTHING` or `BROKE`.
    """
    if not grid.in_bounds(cell):
        return NOTHING
    soil = grid.soil_at(cell)
    if soil.soil_type != "tilled_dirt" or soil.organic_matter >= 1.0:
        return NOTHING
    if not spend_credits(economy, COMPOST_COST):
        return BROKE
    compost_cell(soil)
    conditions.last_treatment = "organic"
    return OK


def apply_spray(
    grid: GardenGrid,
    entity_manager: EntityManager,
    economy: PlayerEconomy,
    conditions: GardenConditions,
    cell: Cell,
) -> str:
    """Spray `cell` and its eight neighbours, if affordable.

    Args:
        grid: The plot.
        entity_manager: Where the plants being marked live.
        economy: Who pays.
        conditions: Records the answer as chemical.
        cell: The centre of the spray.

    Returns:
        `OK`, `NOTHING` or `BROKE`.
    """
    if not grid.in_bounds(cell):
        return NOTHING
    if not spend_credits(economy, SPRAY_COST):
        return BROKE

    for target in [cell, *neighbors8(cell)]:
        if not grid.in_bounds(target):
            continue
        spray_cell(grid.soil_at(target))
        entity_id = grid.plant_at.get(target)
        if entity_id is None:
            continue
        entity = entity_manager.get_entity(entity_id)
        if entity is not None and entity.has_component(PlantComponent):
            entity.get_component(PlantComponent).is_chemical_boosted = True

    conditions.last_treatment = "chemical"
    return OK
