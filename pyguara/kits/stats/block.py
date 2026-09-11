"""A stat container: an open, game-named set of `ModifiableValue`s.

No fixed stat list -- "strength", "armor", "crit chance" are game/kit
vocabulary this deliberately does not impose. A game (or a downstream kit
like `action_combat`) decides what names it puts in.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pyguara.common.modifiers import ModifiableValue
from pyguara.ecs.component import StrictComponent


@dataclass(slots=True)
class StatBlock(StrictComponent):
    """Pure data: an entity's named stats, each a `ModifiableValue`.

    All behavior -- reading a value, stacking a modifier, removing every
    modifier a given source contributed -- already lives on
    `ModifiableValue` itself (`pyguara.common.modifiers`); this component
    only holds the dict. `get_stat()` below is a convenience for the
    common "read with a default" case, not a wrapper around every
    `ModifiableValue` method.

    Attributes:
        stats: Stat name to its `ModifiableValue`. A name absent from this
            dict simply doesn't exist yet -- see `get_stat()`'s default.
    """

    stats: dict[str, ModifiableValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a zero-argument
        `super()` still resolves against the discarded original, raising
        TypeError on every instantiation.
        """
        StrictComponent.__init__(self)


def get_stat(block: StatBlock, name: str, default: float = 0.0) -> float:
    """Return `name`'s current value, or `default` if the stat doesn't exist.

    Args:
        block: The stat container to read.
        name: The stat's name.
        default: Value to return when `name` isn't in `block.stats`.
    """
    stat = block.stats.get(name)
    return stat.value if stat is not None else default
