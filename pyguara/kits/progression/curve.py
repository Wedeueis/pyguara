"""How much experience each level costs.

A `Protocol`, not an ABC, per the repo's structural-subtyping convention:
a game with a bespoke progression writes one method and passes it, with
nothing to import and nothing to inherit from.

Three implementations ship, which is the right number. `Linear` and
`Geometric` cover the two shapes almost every curve is drawn from, and
`Table` covers "the designer typed the numbers in a spreadsheet". Anything
past that is one method.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@runtime_checkable
class LevelCurve(Protocol):
    """Maps a level to the experience needed to leave it.

    Levels are 1-based: `cost_for(1)` is what it takes to reach level 2.
    """

    def cost_for(self, level: int) -> float:
        """Return the experience needed to advance *from* `level`.

        Args:
            level: The level being left, 1-based.

        Returns:
            Experience required. Must be positive -- a zero or negative
            cost would let one grant advance unbounded levels.
        """
        ...


@dataclass(frozen=True)
class Linear:
    """Each level costs a fixed amount more than the one before.

    `base + step * (level - 1)`: level 1 costs `base`, level 2 costs
    `base + step`, and so on.

    Attributes:
        base: Cost of the first level.
        step: How much each subsequent level adds.
    """

    base: float = 100.0
    step: float = 50.0

    def cost_for(self, level: int) -> float:
        """Return the experience needed to advance from `level`."""
        return max(1e-9, self.base + self.step * (level - 1))


@dataclass(frozen=True)
class Geometric:
    """Each level costs a fixed *multiple* of the one before.

    `base * growth ** (level - 1)`. The usual shape for a run that is
    meant to slow down rather than stop.

    Attributes:
        base: Cost of the first level.
        growth: Multiplier per level. 1.0 is flat; below 1.0 accelerates.
    """

    base: float = 100.0
    growth: float = 1.25

    def cost_for(self, level: int) -> float:
        """Return the experience needed to advance from `level`."""
        return max(1e-9, self.base * (self.growth ** (level - 1)))


@dataclass(frozen=True)
class Table:
    """Costs read straight off a list a designer wrote.

    Past the end of the list the last entry repeats, so a table need only
    describe the levels worth hand-tuning and the curve still answers for
    a run that outlasts it.

    Attributes:
        costs: Cost of level 1 first. Must not be empty.
    """

    costs: list[float] = field(default_factory=lambda: [100.0])

    def cost_for(self, level: int) -> float:
        """Return the experience needed to advance from `level`."""
        if not self.costs:
            raise ValueError("Table: costs must not be empty")
        index = min(max(level, 1), len(self.costs)) - 1
        return max(1e-9, self.costs[index])
