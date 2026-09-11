"""Tests for `pyguara/kits/stats/` (StatBlock, DamageType, formulas)."""

from __future__ import annotations

from pyguara.common.modifiers import ModifiableValue, Modifier, ModifierType
from pyguara.ecs.manager import EntityManager
from pyguara.kits.stats import (
    DamageType,
    StatBlock,
    apply_luck_to_chance,
    effective_defense,
    get_stat,
    mitigation_from_defense,
)

# ========== DamageType ==========


def test_damage_type_has_the_three_mitigation_relevant_categories() -> None:
    assert {t.value for t in DamageType} == {"physical", "elemental", "true"}


# ========== formulas: effective_defense ==========


def test_effective_defense_with_no_pierce_is_unchanged() -> None:
    assert effective_defense(100.0, pierce_fraction=0.0) == 100.0


def test_effective_defense_with_full_pierce_is_zero() -> None:
    assert effective_defense(100.0, pierce_fraction=1.0) == 0.0


def test_effective_defense_with_partial_pierce() -> None:
    assert effective_defense(100.0, pierce_fraction=0.3) == 70.0


# ========== formulas: mitigation_from_defense ==========


def test_zero_defense_mitigates_nothing() -> None:
    assert mitigation_from_defense(0.0, scaling=50.0) == 0.0


def test_negative_defense_mitigates_nothing() -> None:
    assert mitigation_from_defense(-10.0, scaling=50.0) == 0.0


def test_defense_equal_to_scaling_is_exactly_half_mitigation() -> None:
    assert mitigation_from_defense(50.0, scaling=50.0) == 0.5


def test_mitigation_approaches_but_never_reaches_one() -> None:
    result = mitigation_from_defense(1_000_000.0, scaling=50.0)
    assert 0.999 < result < 1.0


def test_mitigation_increases_monotonically_with_defense() -> None:
    low = mitigation_from_defense(10.0, scaling=50.0)
    high = mitigation_from_defense(100.0, scaling=50.0)
    assert high > low


# ========== formulas: apply_luck_to_chance ==========


def test_zero_luck_leaves_chance_unchanged() -> None:
    assert apply_luck_to_chance(0.2, luck=0.0) == 0.2


def test_positive_luck_raises_the_chance() -> None:
    assert apply_luck_to_chance(0.2, luck=0.25) == 0.25


def test_negative_luck_lowers_the_chance() -> None:
    assert apply_luck_to_chance(0.2, luck=-0.5) == 0.1


def test_chance_is_clamped_to_one() -> None:
    assert apply_luck_to_chance(0.9, luck=1.0) == 1.0


def test_chance_is_clamped_to_zero() -> None:
    assert apply_luck_to_chance(0.1, luck=-2.0) == 0.0


# ========== StatBlock / get_stat ==========


def test_get_stat_of_a_missing_name_returns_the_default() -> None:
    block = StatBlock()

    assert get_stat(block, "armor") == 0.0
    assert get_stat(block, "armor", default=5.0) == 5.0


def test_get_stat_reads_the_modifiable_values_value() -> None:
    block = StatBlock(stats={"armor": ModifiableValue(10.0)})

    assert get_stat(block, "armor") == 10.0


def test_each_stat_block_gets_its_own_dict() -> None:
    """The classic mutable-default-factory bug: two instances must not
    share the same underlying dict."""
    a = StatBlock()
    b = StatBlock()

    a.stats["armor"] = ModifiableValue(10.0)

    assert "armor" not in b.stats


def test_modifiers_applied_through_the_block_are_visible_via_get_stat() -> None:
    block = StatBlock(stats={"armor": ModifiableValue(10.0)})

    block.stats["armor"].add_modifier(Modifier(5.0, ModifierType.FLAT, source="ring"))
    assert get_stat(block, "armor") == 15.0

    block.stats["armor"].remove_source("ring")
    assert get_stat(block, "armor") == 10.0


def test_stat_block_attaches_to_an_entity() -> None:
    manager = EntityManager()
    entity = manager.create_entity()

    entity.add_component(StatBlock(stats={"hp": ModifiableValue(100.0)}))

    assert entity.has_component(StatBlock)
    assert get_stat(entity.get_component(StatBlock), "hp") == 100.0
