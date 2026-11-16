"""The loot kit: drop tables, rarity, weighted rolls.

`Rarity`/`roll_rarity()` and `LootEntry`/`LootTable`/`roll_loot()`
build on `pyguara.common.random.weighted_choice()`, re-exported here.
`roll_rarity()`'s luck adjustment has the same `weight * (1 + luck)`
shape as `kits.stats.apply_luck_to_chance`, applied across a multi-way
roll.
"""

from pyguara.common.random import weighted_choice
from pyguara.kits.loot.rarity import DEFAULT_RARITY_WEIGHTS, Rarity, roll_rarity
from pyguara.kits.loot.table import LootEntry, LootTable, roll_loot

__all__ = [
    "DEFAULT_RARITY_WEIGHTS",
    "LootEntry",
    "LootTable",
    "Rarity",
    "roll_loot",
    "roll_rarity",
    "weighted_choice",
]
