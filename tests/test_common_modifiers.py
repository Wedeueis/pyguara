"""Tests for `pyguara/common/modifiers.py` (Modifier, ModifiableValue)."""

from __future__ import annotations

from pyguara.common.modifiers import ModifiableValue, Modifier, ModifierType


def test_no_modifiers_returns_base() -> None:
    v = ModifiableValue(10.0)

    assert v.value == 10.0


def test_flat_modifiers_sum_and_add_to_base() -> None:
    v = ModifiableValue(10.0)
    v.add_modifier(Modifier(5.0, ModifierType.FLAT, source="a"))
    v.add_modifier(Modifier(-2.0, ModifierType.FLAT, source="b"))

    assert v.value == 13.0


def test_percent_add_modifiers_sum_then_apply_once() -> None:
    v = ModifiableValue(10.0)
    v.add_modifier(Modifier(0.1, ModifierType.PERCENT_ADD, source="a"))
    v.add_modifier(Modifier(0.2, ModifierType.PERCENT_ADD, source="b"))

    # 10 * (1 + 0.1 + 0.2) == 13.0, not 10 * 1.1 * 1.2
    assert v.value == 13.0


def test_percent_mult_modifiers_compound_in_sequence() -> None:
    v = ModifiableValue(10.0)
    v.add_modifier(Modifier(0.1, ModifierType.PERCENT_MULT, source="a"))
    v.add_modifier(Modifier(0.2, ModifierType.PERCENT_MULT, source="b"))

    # 10 * 1.1 * 1.2 == 13.2, not 10 * (1 + 0.1 + 0.2)
    assert round(v.value, 6) == 13.2


def test_flat_applies_before_percent_add() -> None:
    v = ModifiableValue(10.0)
    v.add_modifier(Modifier(10.0, ModifierType.FLAT, source="a"))
    v.add_modifier(Modifier(0.5, ModifierType.PERCENT_ADD, source="b"))

    # (10 + 10) * 1.5 == 30.0
    assert v.value == 30.0


def test_full_stack_combines_in_the_documented_order() -> None:
    v = ModifiableValue(10.0)
    v.add_modifier(Modifier(5.0, ModifierType.FLAT, source="a"))
    v.add_modifier(Modifier(0.2, ModifierType.PERCENT_ADD, source="b"))
    v.add_modifier(Modifier(0.1, ModifierType.PERCENT_MULT, source="c"))

    # (10 + 5) * (1 + 0.2) * (1 + 0.1) == 19.8
    assert round(v.value, 6) == 19.8


def test_override_short_circuits_everything_else() -> None:
    v = ModifiableValue(10.0)
    v.add_modifier(Modifier(999.0, ModifierType.FLAT, source="a"))
    v.add_modifier(Modifier(42.0, ModifierType.OVERRIDE, source="b"))

    assert v.value == 42.0


def test_most_recently_added_override_wins() -> None:
    v = ModifiableValue(10.0)
    v.add_modifier(Modifier(1.0, ModifierType.OVERRIDE, source="a"))
    v.add_modifier(Modifier(2.0, ModifierType.OVERRIDE, source="b"))

    assert v.value == 2.0


def test_removing_the_active_override_falls_back_to_the_remaining_stack() -> None:
    v = ModifiableValue(10.0)
    v.add_modifier(Modifier(5.0, ModifierType.FLAT, source="a"))
    v.add_modifier(Modifier(1.0, ModifierType.OVERRIDE, source="b"))

    v.remove_source("b")

    assert v.value == 15.0


def test_remove_source_deletes_every_modifier_from_that_source() -> None:
    v = ModifiableValue(10.0)
    v.add_modifier(Modifier(5.0, ModifierType.FLAT, source="item"))
    v.add_modifier(Modifier(0.5, ModifierType.PERCENT_ADD, source="item"))
    v.add_modifier(Modifier(3.0, ModifierType.FLAT, source="other"))

    removed = v.remove_source("item")

    assert removed == 2
    assert v.value == 13.0  # only the "other" flat +3 remains


def test_remove_source_of_an_absent_source_is_a_noop() -> None:
    v = ModifiableValue(10.0)
    v.add_modifier(Modifier(5.0, ModifierType.FLAT, source="a"))

    removed = v.remove_source("never added")

    assert removed == 0
    assert v.value == 15.0


def test_sources_reports_distinct_sources_currently_applied() -> None:
    v = ModifiableValue(10.0)
    v.add_modifier(Modifier(5.0, ModifierType.FLAT, source="a"))
    v.add_modifier(Modifier(0.1, ModifierType.PERCENT_ADD, source="a"))
    v.add_modifier(Modifier(1.0, ModifierType.FLAT, source="b"))

    assert v.sources() == {"a", "b"}


def test_setting_base_invalidates_the_cache() -> None:
    v = ModifiableValue(10.0)
    assert v.value == 10.0

    v.base = 20.0

    assert v.value == 20.0


def test_value_is_cached_between_reads() -> None:
    v = ModifiableValue(10.0)
    v.add_modifier(Modifier(5.0, ModifierType.FLAT, source="a"))

    first = v.value
    second = v.value

    assert first == second == 15.0
