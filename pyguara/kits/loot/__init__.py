"""#28's loot kit, the last one on its kits table: drop tables, rarity, weighted rolls.

`weighted_choice()` is the fully generic core; `Rarity`/`roll_rarity()`
and `LootEntry`/`LootTable`/`roll_loot()` build on it. `roll_rarity()`'s
luck adjustment is the `kits/stats` dependency #28 names -- the same
`weight * (1 + luck)` shape as `kits.stats.apply_luck_to_chance`, applied
across a multi-way roll instead of a single chance.
"""

from pyguara.kits.loot.rarity import DEFAULT_RARITY_WEIGHTS, Rarity, roll_rarity
from pyguara.kits.loot.table import LootEntry, LootTable, roll_loot
from pyguara.kits.loot.weighted_choice import weighted_choice

__all__ = [
    "DEFAULT_RARITY_WEIGHTS",
    "LootEntry",
    "LootTable",
    "Rarity",
    "roll_loot",
    "roll_rarity",
    "weighted_choice",
]
