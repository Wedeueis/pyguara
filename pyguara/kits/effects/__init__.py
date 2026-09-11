"""#28's effects kit: the generic item/boon/equipment-module substrate.

`Effect` is a plain, overridable domain object -- no fixed subtypes or
categories (`reclaimer_legacy` baked in four; that's game data here).
`EffectContainer` is a pure-data component holding a list of them;
`add_effect()`/`remove_effect()` do the actual apply/remove orchestration
and stacking-rule handling, and `EffectSystem` ticks active effects each
frame. Reacts to events from *any* kit -- an effect subscribes to whatever
event it cares about (`kits.action_combat.DamageDealt`, a procgen
room-entry event, anything) through core event dispatch in its own
`on_apply()`; this kit never imports another kit to do it.
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
