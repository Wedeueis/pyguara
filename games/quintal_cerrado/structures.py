"""The automation tech tree: what the store sells, and how it is placed.

The PRD's four structures, in the order it lists them, each unlocking the
next kind of chore it takes off the player's hands:

- **Solar Micro-Panel** -- passive Sementes, and the power everything else
  runs on. Nothing needs power to be *placed*, only to *work*.
- **Drip Irrigation** -- keeps the soil around it above the moisture line
  plants need, so watering stops being a chore. Needs power.
- **Syntropic Soil Sensor** -- reads moisture, organic matter and pest
  pressure onto the tiles around it. Needs no power.
- **Auto-Harvester Drone** -- harvests ready plants around it and sells
  them. Needs power.

A structure is a purchase, then a placement: the store puts it in
`PlayerEconomy.inventory` and the player clicks a cell to put it down.
Placing a kind for the first time records it in `unlocked_tech`, which is
what gates the next structure (`Structure.requires`) -- so the tree is
something you *build* your way up, not merely pay for.
"""

from __future__ import annotations

from dataclasses import dataclass

from games.quintal_cerrado.components import (
    AutomationComponent,
    PlayerEconomy,
    spend_credits,
)
from games.quintal_cerrado.garden_grid import GardenGrid
from pyguara.common.grid import Cell
from pyguara.common.types import Color
from pyguara.ecs.manager import EntityManager
from pyguara.ui.design_system.tokens import Sand, Verdant, Water

POWER_PER_PANEL = 3
"""How many powered devices (drip nozzles, drones) one solar panel runs."""

OK = "ok"
NOTHING = "nothing"
LOCKED = "locked"
BROKE = "broke"
"""The ways buying or placing can end. `NOTHING` charges and consumes
nothing: the cell was taken or out of bounds, or there was none in stock."""


@dataclass(frozen=True)
class Structure:
    """One structure's static data.

    Attributes:
        kind: Stable id, matching `AutomationComponent.kind`.
        display_name: What the store and messages call it.
        description: One line for the store card.
        cost: Sementes to buy one.
        radius: How many cells out (Chebyshev) it reaches, so 1 is a 3x3.
        needs_power: Whether it only works while a panel powers it.
        requires: The kind that must have been placed before this one can be
            bought, or None if it is available from the start.
        color: The structure's accent colour (this demo ships no textures).
    """

    kind: str
    display_name: str
    description: str
    cost: int
    radius: int
    needs_power: bool
    requires: str | None
    color: Color


STRUCTURE_TABLE: dict[str, Structure] = {
    "solar_panel": Structure(
        kind="solar_panel",
        display_name="Solar Micro-Panel",
        description="Earns Sementes on its own, and powers 3 devices.",
        cost=40,
        radius=0,
        needs_power=False,
        requires=None,
        color=Color(70, 110, 170),
    ),
    "drip_irrigation": Structure(
        kind="drip_irrigation",
        display_name="Drip Irrigation",
        description="Keeps the 3x3 around it watered. Needs power.",
        cost=40,
        radius=1,
        needs_power=True,
        requires="solar_panel",
        color=Water.C300,
    ),
    "soil_sensor": Structure(
        kind="soil_sensor",
        display_name="Soil Sensor",
        description="Shows moisture, humus and pests within 2 tiles.",
        cost=30,
        radius=2,
        needs_power=False,
        requires="drip_irrigation",
        color=Verdant.SAGE_100,
    ),
    "auto_harvester": Structure(
        kind="auto_harvester",
        display_name="Harvester Drone",
        description="Harvests and sells ready crops in its 3x3. Needs power.",
        cost=90,
        radius=1,
        needs_power=True,
        requires="soil_sensor",
        color=Sand.C300,
    ),
}


def is_unlocked(economy: PlayerEconomy, kind: str) -> bool:
    """Whether the player may buy `kind` yet.

    Args:
        economy: The player's economy.
        kind: A key of `STRUCTURE_TABLE`.

    Returns:
        True if it has no requirement, or its requirement has been placed.
    """
    requires = STRUCTURE_TABLE[kind].requires
    return requires is None or requires in economy.unlocked_tech


def buy_structure(economy: PlayerEconomy, kind: str) -> str:
    """Buy one `kind` into the inventory.

    Args:
        economy: Who pays.
        kind: A key of `STRUCTURE_TABLE`.

    Returns:
        `OK`, `LOCKED` (its requirement has not been placed) or `BROKE`.
    """
    if not is_unlocked(economy, kind):
        return LOCKED
    if not spend_credits(economy, STRUCTURE_TABLE[kind].cost):
        return BROKE
    economy.inventory[kind] = economy.inventory.get(kind, 0) + 1
    return OK


def place_structure(
    grid: GardenGrid,
    entity_manager: EntityManager,
    economy: PlayerEconomy,
    kind: str,
    cell: Cell,
) -> str:
    """Put a structure from the inventory down on `cell`.

    Args:
        grid: The plot.
        entity_manager: Where the new structure entity is created.
        economy: Whose inventory it comes from.
        kind: A key of `STRUCTURE_TABLE`.
        cell: Where to put it.

    Returns:
        `OK`, or `NOTHING` if there is none in stock or the cell cannot
        take one.
    """
    if economy.inventory.get(kind, 0) <= 0 or not grid.can_build(cell):
        return NOTHING
    entity = entity_manager.create_entity()
    entity.add_component(AutomationComponent(kind=kind))
    grid.mark_built(cell, entity.id)
    economy.inventory[kind] -= 1
    economy.unlocked_tech.add(kind)
    return OK


def area(grid: GardenGrid, cell: Cell, radius: int) -> list[Cell]:
    """Every in-bounds cell within `radius` of `cell` (Chebyshev), itself included.

    Args:
        grid: The plot, for its bounds.
        cell: The centre.
        radius: How far out to reach.

    Returns:
        The cells, row by row.
    """
    x, y = cell
    return [
        (cx, cy)
        for cy in range(y - radius, y + radius + 1)
        for cx in range(x - radius, x + radius + 1)
        if grid.in_bounds((cx, cy))
    ]
