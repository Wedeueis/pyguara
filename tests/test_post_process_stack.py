"""Bookkeeping tests for the post-process stack.

`PostProcessStack` and `RenderGraph` are siblings with the same design -- an
ordered list plus name lookup -- and they carried the same two defects. The
graph's were fixed in the pipeline slice; these are the stack's.

Only the bookkeeping is covered here. Applying an effect needs a live GL
context and stays with the ModernGL integration tests.
"""

from unittest.mock import MagicMock

from pyguara.graphics.vfx.post_process import PostProcessStack


def make_effect(name: str) -> MagicMock:
    effect = MagicMock()
    effect.name = name
    effect.enabled = True
    return effect


def make_stack() -> PostProcessStack:
    return PostProcessStack(MagicMock(), MagicMock())


class TestEffectOrdering:
    def test_effects_are_returned_in_insertion_order(self) -> None:
        stack = make_stack()
        first, second = make_effect("bloom"), make_effect("vignette")
        stack.add_effect(first)
        stack.add_effect(second)

        assert stack.effects == [first, second]

    def test_insert_effect_positions_it(self) -> None:
        stack = make_stack()
        stack.add_effect(make_effect("vignette"))
        early = make_effect("bloom")
        stack.insert_effect(0, early)

        assert stack.effects[0] is early


class TestEffectListEncapsulation:
    def test_the_returned_list_is_a_snapshot(self) -> None:
        """`effects` handed back the live list, so a caller could empty the
        stack without releasing a single effect."""
        stack = make_stack()
        stack.add_effect(make_effect("bloom"))

        stack.effects.clear()

        assert len(stack.effects) == 1

    def test_mutating_the_snapshot_does_not_reorder_the_stack(self) -> None:
        stack = make_stack()
        first, second = make_effect("a"), make_effect("b")
        stack.add_effect(first)
        stack.add_effect(second)

        snapshot = stack.effects
        snapshot.reverse()

        assert stack.effects == [first, second]


class TestEffectLookup:
    def test_get_and_remove_by_name(self) -> None:
        stack = make_stack()
        bloom = make_effect("bloom")
        stack.add_effect(bloom)

        assert stack.get_effect("bloom") is bloom
        assert stack.remove_effect("bloom") is bloom
        assert stack.get_effect("bloom") is None

    def test_removing_an_unknown_name_returns_none(self) -> None:
        assert make_stack().remove_effect("nope") is None

    def test_a_duplicate_effect_name_is_reported(self, caplog) -> None:
        """Both apply -- the list is the source of truth -- but only the first
        is reachable by name. Same treatment RenderGraph gives duplicate pass
        names."""
        import logging

        stack = make_stack()
        stack.add_effect(make_effect("bloom"))

        with caplog.at_level(logging.WARNING):
            stack.add_effect(make_effect("bloom"))

        assert "second post-process effect named 'bloom'" in caplog.text
        assert len(stack.effects) == 2

    def test_a_unique_name_is_not_reported(self, caplog) -> None:
        import logging

        stack = make_stack()
        stack.add_effect(make_effect("bloom"))

        with caplog.at_level(logging.WARNING):
            stack.add_effect(make_effect("vignette"))

        assert caplog.text == ""

    def test_insert_effect_also_reports_a_duplicate(self, caplog) -> None:
        import logging

        stack = make_stack()
        stack.add_effect(make_effect("bloom"))

        with caplog.at_level(logging.WARNING):
            stack.insert_effect(0, make_effect("bloom"))

        assert "second post-process effect" in caplog.text
