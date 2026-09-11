"""Attribute/stat containers, damage typing, and resist/mitigation math.

The first kit under `pyguara/kits/` (per #28) -- an opt-in, game/kit-level
world model built entirely on core mechanism: `StatBlock` wraps
`pyguara.common.modifiers.ModifiableValue` per stat, and nothing here is
DI-registered or ECS-auto-wired. A game constructs `StatBlock` components
itself and attaches them to whatever entities need stats.

Depended on by `kits/action_combat` (the damage pipeline) and
`kits/loot` (equipment stat bonuses), per #28's kit-dependency notes.
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
