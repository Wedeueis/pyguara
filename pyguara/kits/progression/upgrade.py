"""Upgrades, what an entity has taken, and the pick offered on a level-up.

Two composition decisions carry this module.

**`Upgrade.apply` is an opaque callable.** The kit never learns that
"+10% move speed" means a `StatBlock` modifier, or that "pierce" means an
`Effect` -- the game writes the closure. So this file imports neither
`kits.stats` nor `kits.effects` while composing perfectly with both, and
with whatever a game invents that neither anticipated.

**`offer()` does not reimplement weighted selection.** It filters by
eligibility and delegates to `common.random.weighted_choice`, sampling
without replacement. A kit growing its own subtly different weighting is
how two RNG behaviours end up in one engine.

**Weapon evolution needs no new type.** `requires` plus `UpgradeRecord`
*is* the mechanism: "evolved whip requires whip x5 and the bracer" is a
`requires` of `{"whip": 5, "bracer": 1}`. That is what earns `requires`
its place in an otherwise minimal kit, and it takes evolution trees out of
the "needs an item model" column entirely.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from pyguara.common.random import RandomStream, weighted_choice
from pyguara.ecs.component import StrictComponent


@dataclass(frozen=True)
class Upgrade:
    """One thing a level-up can buy.

    Attributes:
        key: Identifies this upgrade in an `UpgradeRecord` and in other
            upgrades' `requires`. Unique within a pool.
        apply: Called with the taking entity's id when this upgrade is
            taken. Opaque to the kit -- a closure the game writes over
            whatever its stats, effects or weapons actually are.
        weight: Relative odds of being offered, among eligible upgrades.
        max_taken: How many times this may be taken. `None` is unlimited.
        requires: Other upgrades' keys mapped to the number of times each
            must already have been taken. An upgrade is only offered once
            every requirement is met.
    """

    key: str
    apply: Callable[[str], None]
    weight: float = 1.0
    max_taken: int | None = 1
    requires: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class UpgradeRecord(StrictComponent):
    """What an entity has taken, and how many times.

    Attributes:
        taken: Upgrade key to the number of times it has been taken. A key
            absent from this dict has never been taken.
    """

    taken: dict[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Initialise the StrictComponent state the dataclass __init__ skips.

        Calls the base explicitly rather than via `super()`: with
        `slots=True` the decorator returns a *new* class, and a
        zero-argument `super()` still resolves against the discarded
        original, raising TypeError on every instantiation.
        """
        StrictComponent.__init__(self)


def times_taken(record: UpgradeRecord, key: str) -> int:
    """Return how many times `key` has been taken, 0 if never."""
    return record.taken.get(key, 0)


def eligible(upgrade: Upgrade, record: UpgradeRecord) -> bool:
    """Whether `upgrade` may still be offered to `record`'s owner.

    Args:
        upgrade: The upgrade being considered.
        record: What its owner has taken so far.

    Returns:
        True if the upgrade is below its `max_taken` and every entry in
        its `requires` is satisfied.
    """
    if upgrade.max_taken is not None:
        if times_taken(record, upgrade.key) >= upgrade.max_taken:
            return False

    return all(
        times_taken(record, required_key) >= count
        for required_key, count in upgrade.requires.items()
    )


def offer(
    rng: RandomStream,
    pool: Sequence[Upgrade],
    record: UpgradeRecord,
    count: int = 3,
) -> list[Upgrade]:
    """Draw up to `count` distinct eligible upgrades, weighted.

    Sampling is without replacement, so a card cannot appear twice in one
    offer. Selection itself is `common.random.weighted_choice` -- this
    function contributes the eligibility filter and the without-replacement
    loop, and deliberately no weighting logic of its own.

    Args:
        rng: Seeded stream driving the draw. The same seed and the same
            record produce the same offer, which is what lets a run be
            replayed.
        pool: Every upgrade the game defines.
        record: What the entity has taken, for eligibility.
        count: How many to offer. Fewer are returned when fewer are
            eligible -- a late run that has exhausted its pool offers two
            cards rather than raising.

    Returns:
        The drawn upgrades, in the order drawn.
    """
    remaining = [upgrade for upgrade in pool if eligible(upgrade, record)]
    drawn: list[Upgrade] = []

    while remaining and len(drawn) < count:
        choices = [(upgrade, upgrade.weight) for upgrade in remaining]
        if sum(weight for _, weight in choices) <= 0:
            # Every remaining upgrade has zero weight. `weighted_choice`
            # raises on this, correctly; here it just means the pool is
            # spent, which is the same case as running out of cards.
            break
        picked = weighted_choice(rng, choices)
        drawn.append(picked)
        remaining.remove(picked)

    return drawn


def take(record: UpgradeRecord, upgrade: Upgrade, entity_id: str) -> None:
    """Record `upgrade` as taken by `entity_id` and run its effect.

    The order matters: the record is updated first, so an `apply` closure
    that reads the record (an upgrade that scales with its own stack
    count) sees the take it is part of.

    Args:
        record: Updated in place.
        upgrade: The upgrade being taken.
        entity_id: Passed to `upgrade.apply`.
    """
    record.taken[upgrade.key] = times_taken(record, upgrade.key) + 1
    upgrade.apply(entity_id)
