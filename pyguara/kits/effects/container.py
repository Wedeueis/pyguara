"""`EffectContainer`, `StackingRule`, and `add_effect()`/`remove_effect()`.

`EffectContainer` is pure data -- a `StrictComponent` holding one list.
The actual add/remove orchestration (stacking rules, calling an effect's
`on_apply()`/`on_remove()`) lives in the free functions below, the same
split `kits/stats`' `StatBlock`/`get_stat` and `action_combat`'s
`Health`/`apply_damage()` already use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pyguara.ecs.component import StrictComponent
from pyguara.events.dispatcher import EventDispatcher
from pyguara.kits.effects.effect import Effect


class StackingRule(Enum):
    """How `add_effect()` handles an effect whose `key` is already present.

    Attributes:
        STACK: Add another instance alongside any existing ones (up to
            `add_effect()`'s `max_stacks`, if given).
        REFRESH: Reset the existing instance's `elapsed` to 0 instead of
            adding a new one -- a re-applied buff extends its duration
            rather than stacking its magnitude.
        IGNORE: Do nothing while an instance is already present.
        REPLACE: Remove every existing instance sharing the key, then
            apply the new one.
    """

    STACK = "stack"
    REFRESH = "refresh"
    IGNORE = "ignore"
    REPLACE = "replace"


@dataclass(slots=True)
class EffectContainer(StrictComponent):
    """Pure data: the effects currently active on an entity.

    Attributes:
        effects: Active `Effect` instances, in application order.
    """

    effects: list[Effect] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        StrictComponent.__init__(self)


def add_effect(
    dispatcher: EventDispatcher,
    entity_id: str,
    container: EffectContainer,
    effect: Effect,
    stacking: StackingRule = StackingRule.STACK,
    max_stacks: int | None = None,
) -> bool:
    """Add `effect` to `container`, honoring `stacking` against same-key effects.

    Args:
        dispatcher: Forwarded to `effect.on_apply()`, and to `on_remove()`
            for anything `REPLACE` removes.
        entity_id: The entity `container` belongs to, forwarded to
            `on_apply()`/`on_remove()`.
        container: Where to add `effect`.
        effect: The effect to add. Not yet applied -- `on_apply()` hasn't
            run yet when this is called.
        stacking: How to handle an existing effect sharing `effect.key`.
            Ignored (treated as `STACK`) if none exists.
        max_stacks: For `STACK` only: refuse a new instance once this many
            same-key effects are already present. `None` (the default) is
            unlimited.

    Returns:
        True if `effect` is now active -- freshly applied, or an existing
        instance was refreshed to renew it. False if rejected outright:
        `IGNORE` with a match already present, or `STACK` at `max_stacks`.
    """
    existing = [e for e in container.effects if e.key == effect.key]

    if stacking is StackingRule.IGNORE and existing:
        return False

    if stacking is StackingRule.REFRESH and existing:
        existing[0].elapsed = 0.0
        return True

    if stacking is StackingRule.REPLACE:
        for old in list(existing):
            remove_effect(dispatcher, entity_id, container, old)

    if (
        stacking is StackingRule.STACK
        and max_stacks is not None
        and len(existing) >= max_stacks
    ):
        return False

    effect.on_apply(entity_id, dispatcher)
    container.effects.append(effect)
    return True


def remove_effect(
    dispatcher: EventDispatcher,
    entity_id: str,
    container: EffectContainer,
    effect: Effect,
) -> None:
    """Remove `effect` from `container` and call its `on_remove()`.

    A no-op if `effect` isn't actually in `container.effects`.

    Args:
        dispatcher: Forwarded to `effect.on_remove()`.
        entity_id: The entity `container` belongs to, forwarded to
            `on_remove()`.
        container: Where to remove `effect` from.
        effect: The effect to remove.
    """
    if effect not in container.effects:
        return
    container.effects.remove(effect)
    effect.on_remove(entity_id, dispatcher)
