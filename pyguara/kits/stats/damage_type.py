"""The damage-type taxonomy stat mitigation formulas key off."""

from __future__ import annotations

from enum import Enum


class DamageType(Enum):
    """How a hit's damage relates to defensive stats.

    Deliberately minimal -- the three categories `formulas.py`'s mitigation
    curve actually branches on -- not a fantasy elemental wheel (fire, ice,
    poison, ...). A game wanting sub-types layers its own vocabulary
    (an `element` field, say) on top; this only distinguishes what
    mitigates a hit at all.
    """

    PHYSICAL = "physical"
    ELEMENTAL = "elemental"
    TRUE = "true"  # A caller skips mitigation/formulas.py entirely for this one.
