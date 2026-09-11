"""A stacking, source-tracked numeric value: base + flat + percent + override.

Genre-agnostic stacking mechanism, not a stat schema -- `ModifiableValue`
knows nothing of "strength" or "armour" (that vocabulary is `kits/stats`'
job), only how several tagged contributions combine into one number. Mined
from `reclaimer_legacy`'s `game/combat/combat_stats.py` `Stat`/`Modifier`
for the arithmetic and the tracked-source removal shape, with its
character/event-dispatcher coupling stripped out -- this is a plain value
type, like `RandomStream`, not wired to any particular game's event system.

No duration or expiry: a temporary buff is `kits/effects`' job (it removes
its own modifier when its own timer elapses), not something this class
tracks itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ModifierType(Enum):
    """How a `Modifier`'s value combines into a `ModifiableValue`."""

    FLAT = "flat"
    PERCENT_ADD = "percent_add"
    PERCENT_MULT = "percent_mult"
    OVERRIDE = "override"


@dataclass(frozen=True)
class Modifier:
    """One tagged contribution to a `ModifiableValue`.

    Attributes:
        value: The contribution's magnitude. Its meaning depends on
            `mod_type` -- a flat amount, a fraction for the two percent
            types (0.1 for +10%), or the replacement value for OVERRIDE.
        mod_type: How this modifier combines with the others.
        source: Whatever identifies where this modifier came from --
            typically an item id, an effect instance, or a status name.
            Compared with `==`, never by identity, so a plain string works
            as well as an object. `ModifiableValue.remove_source()` removes
            every modifier sharing a source in one call, which is the
            primary removal path: a caller unequipping an item or clearing
            a status doesn't track which individual `Modifier`s it added.
    """

    value: float
    mod_type: ModifierType
    source: Any = None


class ModifiableValue:
    """A base value plus stacking modifiers, recomputed lazily.

    ```python
    strength = ModifiableValue(10.0)
    strength.add_modifier(Modifier(5.0, ModifierType.FLAT, source="ring"))
    strength.add_modifier(Modifier(0.2, ModifierType.PERCENT_ADD, source="buff"))
    strength.value  # (10 + 5) * (1 + 0.2) == 18.0
    strength.remove_source("ring")
    strength.value  # (10 + 0) * (1 + 0.2) == 12.0
    ```
    """

    __slots__ = ("_base", "_modifiers", "_cached_value")

    def __init__(self, base: float) -> None:
        """Create a value with no modifiers yet.

        Args:
            base: The unmodified value.
        """
        self._base = base
        self._modifiers: list[Modifier] = []
        self._cached_value: float | None = None

    @property
    def base(self) -> float:
        """The unmodified value, before any modifier is applied."""
        return self._base

    @base.setter
    def base(self, value: float) -> None:
        """Set the unmodified value, invalidating the cached result."""
        self._base = value
        self._cached_value = None

    @property
    def value(self) -> float:
        """The fully-combined value, recomputed only when something changed."""
        if self._cached_value is None:
            self._cached_value = self._compute()
        return self._cached_value

    def add_modifier(self, modifier: Modifier) -> None:
        """Add a modifier, invalidating the cached result."""
        self._modifiers.append(modifier)
        self._cached_value = None

    def remove_source(self, source: Any) -> int:
        """Remove every modifier tagged with `source`.

        Args:
            source: The source to remove, compared with `==`.

        Returns:
            How many modifiers were removed. 0 leaves the cache untouched.
        """
        kept = [m for m in self._modifiers if m.source != source]
        removed = len(self._modifiers) - len(kept)
        if removed:
            self._modifiers = kept
            self._cached_value = None
        return removed

    def sources(self) -> set[Any]:
        """Return the distinct sources of every modifier currently applied."""
        return {m.source for m in self._modifiers}

    def _compute(self) -> float:
        """Combine `base` and every modifier into one value.

        An OVERRIDE modifier short-circuits everything else -- the most
        recently added one wins if several are present, since it's the
        instruction that most recently took effect. Otherwise: flat
        modifiers sum and add to `base`; percent-additive modifiers sum
        and apply once as a single multiplier; percent-multiplicative
        modifiers each apply in sequence, compounding rather than summing.
        """
        overrides = [m for m in self._modifiers if m.mod_type is ModifierType.OVERRIDE]
        if overrides:
            return overrides[-1].value

        flat = sum(m.value for m in self._modifiers if m.mod_type is ModifierType.FLAT)
        percent_add = sum(
            m.value for m in self._modifiers if m.mod_type is ModifierType.PERCENT_ADD
        )
        result = (self._base + flat) * (1 + percent_add)

        for modifier in self._modifiers:
            if modifier.mod_type is ModifierType.PERCENT_MULT:
                result *= 1 + modifier.value

        return result
