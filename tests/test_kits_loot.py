"""Tests for `pyguara/kits/loot/` (weighted_choice, Rarity/roll_rarity,
LootEntry/LootTable/roll_loot)."""

from __future__ import annotations

import pytest

from pyguara.common.random import RandomStream
from pyguara.kits.loot import (
    DEFAULT_RARITY_WEIGHTS,
    LootEntry,
    LootTable,
    Rarity,
    roll_loot,
    roll_rarity,
    weighted_choice,
)

# ========== weighted_choice ==========


def test_single_choice_always_returns_it() -> None:
    rng = RandomStream(1)

    for _ in range(20):
        assert weighted_choice(rng, [("only", 1.0)]) == "only"


def test_zero_weight_item_is_never_picked() -> None:
    rng = RandomStream(1)

    results = {weighted_choice(rng, [("a", 1.0), ("b", 0.0)]) for _ in range(200)}

    assert results == {"a"}


def test_weighted_choice_is_deterministic() -> None:
    choices = [("a", 1.0), ("b", 2.0), ("c", 3.0)]

    a = [weighted_choice(RandomStream(7), choices) for _ in range(20)]
    b = [weighted_choice(RandomStream(7), choices) for _ in range(20)]

    assert a == b


def test_weighted_choice_distribution_roughly_matches_weights() -> None:
    rng = RandomStream(123)
    results = [
        weighted_choice(rng, [("common", 9.0), ("rare", 1.0)]) for _ in range(1000)
    ]

    rare_fraction = results.count("rare") / len(results)
    assert 0.05 < rare_fraction < 0.15  # expected ~0.10


def test_weighted_choice_rejects_empty_choices() -> None:
    with pytest.raises(ValueError, match="empty"):
        weighted_choice(RandomStream(1), [])


def test_weighted_choice_rejects_non_positive_total_weight() -> None:
    with pytest.raises(ValueError, match="positive"):
        weighted_choice(RandomStream(1), [("a", 0.0), ("b", 0.0)])


# ========== Rarity / roll_rarity ==========


def test_default_rarity_weights_cover_every_tier() -> None:
    assert set(DEFAULT_RARITY_WEIGHTS.keys()) == set(Rarity)


def test_roll_rarity_is_deterministic() -> None:
    a = [roll_rarity(RandomStream(9)) for _ in range(20)]
    b = [roll_rarity(RandomStream(9)) for _ in range(20)]

    assert a == b


def test_very_low_luck_always_rolls_common() -> None:
    """luck <= -1.0 clamps every non-COMMON weight to 0."""
    rng = RandomStream(1)

    results = {roll_rarity(rng, luck=-1.0) for _ in range(200)}

    assert results == {Rarity.COMMON}


def test_high_luck_makes_common_rare_relative_to_the_others() -> None:
    rng = RandomStream(1)

    results = [roll_rarity(rng, luck=1000.0) for _ in range(500)]

    common_fraction = results.count(Rarity.COMMON) / len(results)
    assert common_fraction < 0.05


def test_custom_weights_restrict_which_tiers_can_roll() -> None:
    rng = RandomStream(1)
    weights = {Rarity.COMMON: 1.0, Rarity.LEGENDARY: 1.0}

    results = {roll_rarity(rng, weights=weights) for _ in range(200)}

    assert results <= {Rarity.COMMON, Rarity.LEGENDARY}


def test_a_tier_missing_from_custom_weights_is_never_rolled() -> None:
    rng = RandomStream(1)
    weights = {Rarity.COMMON: 1.0}

    results = {roll_rarity(rng, weights=weights) for _ in range(50)}

    assert results == {Rarity.COMMON}


# ========== LootTable / roll_loot ==========


def test_roll_loot_on_an_empty_table_returns_none() -> None:
    assert roll_loot(RandomStream(1), LootTable()) is None


def test_single_entry_table_always_returns_it() -> None:
    entry = LootEntry(payload="sword", weight=1.0)
    table = LootTable(entries=[entry])
    rng = RandomStream(1)

    for _ in range(20):
        assert roll_loot(rng, table) is entry


def test_roll_loot_preserves_payload_and_rarity() -> None:
    entry = LootEntry(payload={"id": "ring_of_luck"}, rarity=Rarity.EPIC)
    table = LootTable(entries=[entry])

    result = roll_loot(RandomStream(1), table)

    assert result is not None
    assert result.payload == {"id": "ring_of_luck"}
    assert result.rarity == Rarity.EPIC


def test_roll_loot_is_deterministic() -> None:
    table = LootTable(
        entries=[
            LootEntry(payload="a", weight=1.0),
            LootEntry(payload="b", weight=2.0),
            LootEntry(payload="c", weight=3.0),
        ]
    )

    a = [roll_loot(RandomStream(42), table).payload for _ in range(20)]
    b = [roll_loot(RandomStream(42), table).payload for _ in range(20)]

    assert a == b


def test_roll_loot_distribution_roughly_matches_weights() -> None:
    table = LootTable(
        entries=[
            LootEntry(payload="common", weight=9.0),
            LootEntry(payload="rare", weight=1.0),
        ]
    )
    rng = RandomStream(123)

    results = [roll_loot(rng, table).payload for _ in range(1000)]

    rare_fraction = results.count("rare") / len(results)
    assert 0.05 < rare_fraction < 0.15
