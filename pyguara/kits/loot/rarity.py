"""`Rarity` and its luck-adjusted roll.

A standard 5-tier scale, unlike `kits/effects`' categories (which #28
explicitly said not to hardcode) -- rarity tiers named this way are a
near-universal RPG-loot convention, not one game's particular vocabulary.
"""

from __future__ import annotations

from enum import Enum

from pyguara.common.random import RandomStream, weighted_choice


class Rarity(Enum):
    """A loot tier, rarest last."""

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


DEFAULT_RARITY_WEIGHTS: dict[Rarity, float] = {
    Rarity.COMMON: 100.0,
    Rarity.UNCOMMON: 50.0,
    Rarity.RARE: 20.0,
    Rarity.EPIC: 8.0,
    Rarity.LEGENDARY: 2.0,
}


def roll_rarity(
    rng: RandomStream,
    luck: float = 0.0,
    weights: dict[Rarity, float] | None = None,
) -> Rarity:
    """Roll a rarity tier, with `luck` boosting every non-`COMMON` tier's odds.

    The `kits.stats` dependency #28 names: same shape as
    `kits.stats.apply_luck_to_chance` (`weight * (1 + luck)`), applied
    across a multi-way weighted roll instead of a single chance.

    Args:
        rng: Seeded stream driving the roll.
        luck: Multiplies every non-`COMMON` tier's weight by `(1 + luck)`,
            clamped at 0. 0.0 (the default) leaves the base weights
            untouched; a negative `luck` lowers rare-tier odds instead,
            down to 0 at `luck <= -1.0`.
        weights: Base weight per tier. Defaults to
            `DEFAULT_RARITY_WEIGHTS`; a tier missing from a custom dict is
            never rolled.

    Returns:
        The rolled tier.
    """
    base = weights if weights is not None else DEFAULT_RARITY_WEIGHTS
    adjusted = [
        (
            rarity,
            weight if rarity is Rarity.COMMON else max(0.0, weight * (1.0 + luck)),
        )
        for rarity, weight in base.items()
    ]
    return weighted_choice(rng, adjusted)
