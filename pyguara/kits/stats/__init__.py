"""Attribute/stat containers, damage typing, and resist/mitigation math.

`StatBlock` wraps a `pyguara.common.modifiers.ModifiableValue` per
stat. Nothing here is registered in the container or wired into the
ECS: a game constructs `StatBlock` components and attaches them.

`kits/action_combat` (the damage pipeline) and `kits/loot` (equipment
stat bonuses) depend on this kit.
"""

from pyguara.kits.stats.block import StatBlock, get_stat
from pyguara.kits.stats.damage_type import DamageType
from pyguara.kits.stats.formulas import (
    apply_luck_to_chance,
    effective_defense,
    mitigation_from_defense,
)

__all__ = [
    "DamageType",
    "StatBlock",
    "apply_luck_to_chance",
    "effective_defense",
    "get_stat",
    "mitigation_from_defense",
]
