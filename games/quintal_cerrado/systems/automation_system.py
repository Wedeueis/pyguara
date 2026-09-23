"""Runs the placed structures: power, solar income, drip watering, drones.

One system for all four, since they share one thing -- the power budget --
and splitting it would mean two systems agreeing on who is powered.

Each tick, first the budget: every solar panel powers `POWER_PER_PANEL`
devices, handed out in the order the structures were placed (a dict keeps
insertion order), so what loses power when a plot is short is the newest
device, not a random one. A device that needs power and does not get it
does nothing and is drawn with a warning; a sensor or panel needs none.

Then the work:

- **Solar panel** -- every `SOLAR_INTERVAL` seconds, `SOLAR_YIELD` Sementes,
  announced with a `SolarIncomeEvent` so the scene can float a "+2".
- **Drip irrigation** -- raises the moisture of every cell in reach towards
  `DRIP_TARGET`, the PRD's "above 60%", and no further: it maintains, it
  does not flood.
- **Harvester drone** -- every `DRONE_INTERVAL` seconds, collects one ready
  plant in reach through `economy.harvest_cell`, the same function the
  harvest tool uses, and announces it with a `PlantHarvestedEvent`. An
  infested plant is not "ready": `harvest_cell` refuses it. A drone pulls
  weeds and collects overripe seed the same as it sells a ready crop --
  `harvest_cell` decides which, this system just reports what it got.

Registered right after `SoilSystem` (see `scenes.py`), so the soil has
evaporated for the tick before drip irrigation tops it back up.
"""

from __future__ import annotations

from games.quintal_cerrado.components import (
    AutomationComponent,
    PlayerEconomy,
    add_credits,
)
from games.quintal_cerrado.economy import harvest_cell
from games.quintal_cerrado.events import PlantHarvestedEvent, SolarIncomeEvent
from games.quintal_cerrado.garden_grid import GardenGrid
from games.quintal_cerrado.structures import POWER_PER_PANEL, STRUCTURE_TABLE, area
from pyguara.common.grid import Cell
from pyguara.ecs.manager import EntityManager
from pyguara.events.dispatcher import EventDispatcher

SOLAR_YIELD = 8
"""Sementes one panel pays a night. A panel (50) earns itself back in about
six days of a twelve-day session, so the first rung of the tree is worth
taking early and not worth taking late."""

DRIP_TARGET = 0.65
"""The moisture drip irrigation holds a cell at (PRD: "above 60%")."""

DRONE_HARVESTS_PER_NIGHT = 2
"""Plants one drone collects a night. Bounded so the drone is a pair of
extra hands, not a replacement for tending the plot."""


class AutomationSystem:
    """Powers, and runs, every placed structure."""

    def __init__(
        self,
        entity_manager: EntityManager,
        grid: GardenGrid,
        economy: PlayerEconomy,
        dispatcher: EventDispatcher,
    ) -> None:
        """Initialize the system.

        Args:
            entity_manager: Where the structure and plant entities live.
            grid: The plot.
            economy: Who solar income and drone sales are paid to.
            dispatcher: Where income and harvests are announced.
        """
        self._entity_manager = entity_manager
        self._grid = grid
        self._economy = economy
        self._dispatcher = dispatcher
        self.power_used = 0
        self.power_capacity = 0

    def resolve_night(self) -> None:
        """Share out power, then run every structure for one tick."""
        structures = self._structures()
        self._allocate_power(structures)
        self.power_capacity = POWER_PER_PANEL * sum(
            1 for _, s in structures if s.kind == "solar_panel"
        )
        self.power_used = sum(
            1
            for _, s in structures
            if s.powered and STRUCTURE_TABLE[s.kind].needs_power
        )
        for cell, structure in structures:
            if not structure.powered:
                continue
            if structure.kind == "solar_panel":
                self._run_solar(cell)
            elif structure.kind == "drip_irrigation":
                self._run_drip(cell)
            elif structure.kind == "auto_harvester":
                self._run_drone(cell)

    def _structures(self) -> list[tuple[Cell, AutomationComponent]]:
        """Every placed structure, in placement order."""
        found = []
        for cell, entity_id in self._grid.automation_at.items():
            entity = self._entity_manager.get_entity(entity_id)
            if entity is not None and entity.has_component(AutomationComponent):
                found.append((cell, entity.get_component(AutomationComponent)))
        return found

    @staticmethod
    def _allocate_power(structures: list[tuple[Cell, AutomationComponent]]) -> None:
        panels = sum(1 for _, s in structures if s.kind == "solar_panel")
        remaining = panels * POWER_PER_PANEL
        for _, structure in structures:
            if not STRUCTURE_TABLE[structure.kind].needs_power:
                structure.powered = True
            elif remaining > 0:
                structure.powered = True
                remaining -= 1
            else:
                structure.powered = False

    def _run_solar(self, cell: Cell) -> None:
        """Pay one panel's night."""
        add_credits(self._economy, SOLAR_YIELD)
        self._dispatcher.dispatch(SolarIncomeEvent(cell=cell, amount=SOLAR_YIELD))

    def _run_drip(self, cell: Cell) -> None:
        """Bring every cell in range up to the target, overnight.

        A night is long enough to fill a nozzle's range, so this is the
        target itself rather than a rate: what the player feels is "the
        drip cells were never dry in the morning".
        """
        for target in area(self._grid, cell, STRUCTURE_TABLE["drip_irrigation"].radius):
            soil = self._grid.soil_at(target)
            if soil.moisture < DRIP_TARGET:
                soil.moisture = DRIP_TARGET

    def _run_drone(self, cell: Cell) -> None:
        """Collect up to `DRONE_HARVESTS_PER_NIGHT` ready plants in range."""
        harvested = 0
        for target in area(self._grid, cell, STRUCTURE_TABLE["auto_harvester"].radius):
            if harvested >= DRONE_HARVESTS_PER_NIGHT:
                return
            result = harvest_cell(
                self._grid, self._entity_manager, self._economy, target
            )
            if result is None:
                continue
            harvested += 1
            self._dispatcher.dispatch(
                PlantHarvestedEvent(
                    cell=target,
                    species_id=result.species_id,
                    value=result.amount,
                    kind=result.kind,
                )
            )
