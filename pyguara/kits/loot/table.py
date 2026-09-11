"""`LootEntry`/`LootTable` and `roll_loot()`.

No drop-count or drop-chance policy baked in -- `roll_loot()` picks one
entry per call; how many times a game calls it (a guaranteed drop plus a
chance at bonus ones, say) is that game's own pacing/economy design, the
same reasoning `kits/spawn`'s budget and pacing stay mechanism rather than
fixed numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyguara.common.random import RandomStream, weighted_choice
from pyguara.kits.loot.rarity import Rarity


@dataclass
class LootEntry:
    """One possible drop in a `LootTable`.

    Attributes:
        payload: Whatever this entry actually represents -- an item id, a
            prefab path, a factory callable. Opaque to this kit.
        weight: This entry's odds relative to the table's other entries.
        rarity: Tag for display/filtering purposes; unrelated to `weight`
            -- pair it with `roll_rarity()` yourself if a table's weights
            should track rarity tiers.
    """

    payload: Any
    weight: float = 1.0
    rarity: Rarity = Rarity.COMMON


@dataclass
class LootTable:
    """A weighted set of possible drops.

    Attributes:
        entries: The possible drops. Order doesn't affect roll odds.
    """

    entries: list[LootEntry] = field(default_factory=list)


def roll_loot(rng: RandomStream, table: LootTable) -> LootEntry | None:
    """Pick one entry from `table`, weighted by each entry's own weight.

    Args:
        rng: Seeded stream driving the roll.
        table: The table to roll against.

    Returns:
        One entry, or `None` if `table` has no entries.
    """
    if not table.entries:
        return None
    return weighted_choice(rng, [(entry, entry.weight) for entry in table.entries])
