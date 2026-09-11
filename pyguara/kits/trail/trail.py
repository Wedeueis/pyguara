"""`Trail`: a growing/shrinking chain of grid cells following a head.

Genre-agnostic: growth is deferred rather than applied immediately (the
classic "eat food, tail doesn't shrink on the next move" pattern) so this
serves any leader-follower chain, not just a snake -- a Tron-style
light-cycle trail, a rope/tail follow mechanic, a visual combo trail.
Built on `pyguara.common.grid.Cell`, no snake vocabulary anywhere here.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field

from pyguara.common.grid import Cell
from pyguara.ecs.component import StrictComponent


@dataclass(slots=True)
class Trail(StrictComponent):
    """A chain of cells, head first, tail last.

    Attributes:
        positions: Occupied cells, index 0 is the head. Empty until
            `reset()` seeds it.
        pending_growth: Segments still owed before the tail resumes
            shrinking on `advance()` -- incremented by `grow()`,
            decremented (not reset) each `advance()` that spends one.
    """

    positions: deque[Cell] = field(default_factory=deque)
    pending_growth: int = 0

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        StrictComponent.__init__(self)

    @property
    def head(self) -> Cell:
        """The lead cell.

        Raises:
            IndexError: `positions` is empty (never `reset()`).
        """
        return self.positions[0]

    @property
    def tail(self) -> Cell:
        """The trailing cell.

        Raises:
            IndexError: `positions` is empty (never `reset()`).
        """
        return self.positions[-1]

    def __len__(self) -> int:
        """Return the number of segments currently occupied."""
        return len(self.positions)


def reset(trail: Trail, cells: Iterable[Cell]) -> None:
    """Replace `trail`'s segments outright, head first, and clear growth debt.

    Args:
        trail: The trail to reset.
        cells: The new segments, head first. Copied, not aliased.
    """
    trail.positions = deque(cells)
    trail.pending_growth = 0


def advance(trail: Trail, new_head: Cell) -> None:
    """Move `trail` forward by one cell.

    Pushes `new_head` onto the front. Pops the tail to keep length
    constant, unless growth is owed (`grow()`), in which case the tail
    stays put for this call and the debt is reduced by one.

    Args:
        trail: The trail to advance. A no-op on length if it was empty
            (`new_head` becomes the only segment either way).
        new_head: The cell the head moves into.
    """
    trail.positions.appendleft(new_head)
    if trail.pending_growth > 0:
        trail.pending_growth -= 1
    else:
        trail.positions.pop()


def grow(trail: Trail, amount: int = 1) -> None:
    """Queue `amount` segments to be added over the next `amount` `advance()` calls.

    Args:
        trail: The trail to grow.
        amount: How many future `advance()` calls should skip popping the
            tail. Must be positive.
    """
    trail.pending_growth += amount


def overlaps_self(trail: Trail) -> bool:
    """Whether the head's cell coincides with any other segment.

    Call after `advance()`, not before: a normal (non-growing) advance
    already pops the vacated tail cell, so moving into where the tail
    just was correctly reads as no collision -- the same rule a manually
    simulated snake needs.
    """
    if len(trail.positions) < 2:
        return False
    head = trail.positions[0]
    return head in list(trail.positions)[1:]


def contains(trail: Trail, cell: Cell) -> bool:
    """Whether `cell` is occupied by any segment of `trail`."""
    return cell in trail.positions
