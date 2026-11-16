"""The effects kit: the generic item, boon and equipment-module substrate.

`Effect` is a plain, overridable domain object with no fixed subtypes;
categories are game data. `EffectContainer` is a data-only component
holding a list of them. `add_effect()` and `remove_effect()` apply and
remove them and handle stacking, and `EffectSystem` ticks active
effects each frame. An effect subscribes to whatever event it cares
about in its own `on_apply()`, through core event dispatch; this kit
imports no other kit.
"""

from pyguara.kits.effects.container import (
    EffectContainer,
    StackingRule,
    add_effect,
    remove_effect,
)
from pyguara.kits.effects.effect import Effect
from pyguara.kits.effects.system import EffectSystem

__all__ = [
    "Effect",
    "EffectContainer",
    "EffectSystem",
    "StackingRule",
    "add_effect",
    "remove_effect",
]
