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
