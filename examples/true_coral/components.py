"""True Coral - ECS Components.

Pure data containers for the snake game. The body itself is
`pyguara.kits.trail.Trail`; everything here is what that kit
deliberately has no vocabulary for.
"""

from dataclasses import dataclass

from pyguara.common.grid import Cell
from pyguara.ecs.component import BaseComponent


@dataclass
class MoveState(BaseComponent):
    """The snake's current heading and its tick-based movement clock.

    Attributes:
        direction: Current heading, a unit grid offset (e.g. `(1, 0)` for
            east). Never `(0, 0)`.
        pending_direction: The next heading queued by input, applied on
            the next tick -- buffered rather than applied immediately so
            two key presses within one tick can't reverse the snake into
            itself (a 180-degree turn is rejected when it's *applied*,
            using the direction actually in effect that tick).
        move_timer: Seconds accumulated since the last grid step. A tick
            fires (possibly several, on a big `dt`) whenever this reaches
            the current move interval.
    """

    direction: Cell = (1, 0)
    pending_direction: Cell | None = None
    move_timer: float = 0.0

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class Food(BaseComponent):
    """One piece of food sitting on the grid.

    Attributes:
        food_type: `"larva"`, `"beetle"`, or `"star"` -- `roll_loot()`'s
            payload from `FOOD_LOOT_TABLE`. Opaque to the loot kit itself;
            this game decides what each name means (growth, points,
            whether it triggers `StarEffect`).
        cell: Where this food sits.
    """

    food_type: str = "larva"
    cell: Cell = (0, 0)

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()


@dataclass
class Score(BaseComponent):
    """Player score tracking."""

    value: int = 0

    def __post_init__(self) -> None:
        """Initialize the component."""
        super().__init__()
