"""The generic weighted-roll primitive `roll_rarity()`/`roll_loot()` build on.

Not loot-specific at all -- lives here because #28 names "weighted rolls"
as one of this kit's three deliverables and nothing else needs it yet.
Promote it to `pyguara/common/` if a second, non-loot consumer ever does;
premature to move it there on spec alone.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pyguara.common.random import RandomStream

T = TypeVar("T")


def weighted_choice(rng: RandomStream, choices: Sequence[tuple[T, float]]) -> T:
    """Pick one item from `choices`, weighted by each entry's own weight.

    Args:
        rng: Seeded stream driving the roll.
        choices: `(item, weight)` pairs. Weights need not sum to 1 -- each
            item's odds are its own weight over the total. A weight of 0
            is never picked (in practice; only an exact floating-point
            boundary hit could select it, which does not happen).

    Returns:
        One item from `choices`.

    Raises:
        ValueError: If `choices` is empty, or every weight is 0 or less.
    """
    if not choices:
        raise ValueError("weighted_choice: choices must not be empty")

    total = sum(weight for _, weight in choices)
    if total <= 0:
        raise ValueError("weighted_choice: total weight must be positive")

    roll = rng.uniform(0, total)
    cumulative = 0.0
    for item, weight in choices:
        cumulative += weight
        if roll <= cumulative:
            return item

    return choices[-1][0]  # Floating-point fallback; should be unreachable.
