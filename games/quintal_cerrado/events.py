"""Quintal do Cerrado - Game Events.

Plain dataclasses, the same shape `guara_falcao/events.py` uses. These are
what let the scene react to `garden_states.py`'s FSM (flash the plot, tell
the player) without the FSM holding a reference to any UI.
"""

from dataclasses import dataclass

from pyguara.common.grid import Cell


@dataclass
class OutbreakStartedEvent:
    """Fired when a pest outbreak begins.

    Attributes:
        cells: The cells the outbreak started on.
    """

    cells: list[Cell]


@dataclass
class OutbreakResolvedEvent:
    """Fired when an outbreak has been cleared.

    Attributes:
        method: `"organic"` or `"chemical"`.
    """

    method: str


@dataclass
class PlantHarvestedEvent:
    """Fired when a harvester drone sells a plant on its own.

    A player's own harvest is handled where it is clicked; a drone acts on
    its own schedule, so the scene learns of it through this.

    Attributes:
        cell: Where the plant was.
        species_id: What it was.
        value: Sementes it sold for.
    """

    cell: Cell
    species_id: str
    value: int


@dataclass
class SolarIncomeEvent:
    """Fired when a solar panel pays out.

    Attributes:
        cell: The panel's cell.
        amount: Sementes paid.
    """

    cell: Cell
    amount: int


@dataclass
class AutosavedEvent:
    """Fired after the periodic autosave runs.

    Attributes:
        success: Whether the save was written.
    """

    success: bool
