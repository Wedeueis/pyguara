"""`Selection` as an ordered set with a primary.

Single-selection behaviour is covered alongside, because the multi-select
widening had to keep `entity_id` and `select()` reading exactly as they did
for the panels that only ever want one entity.
"""

from __future__ import annotations

from pyguara.editor.selection import Selection


class TestSingleSelection:
    """The original contract, which every existing panel depends on."""

    def test_starts_empty(self) -> None:
        selection = Selection()
        assert selection.entity_id is None
        assert selection.entity_ids == ()
        assert len(selection) == 0

    def test_select_sets_the_id(self) -> None:
        selection = Selection()
        selection.select("hero")
        assert selection.entity_id == "hero"
        assert selection.is_selected("hero")

    def test_select_replaces_rather_than_adds(self) -> None:
        """A plain click selects one thing, not one more thing."""
        selection = Selection()
        selection.select("hero")
        selection.select("villain")
        assert selection.entity_ids == ("villain",)

    def test_select_none_clears(self) -> None:
        selection = Selection()
        selection.select("hero")
        selection.select(None)
        assert selection.entity_id is None

    def test_clear_empties(self) -> None:
        selection = Selection()
        selection.select_many(("a", "b"))
        selection.clear()
        assert selection.entity_ids == ()


class TestMultiSelection:
    """Ordered set semantics."""

    def test_add_accumulates_in_order(self) -> None:
        selection = Selection()
        selection.add("a")
        selection.add("b")
        selection.add("c")
        assert selection.entity_ids == ("a", "b", "c")

    def test_the_primary_is_the_most_recently_added(self) -> None:
        """A gizmo anchors to "the last one I clicked"."""
        selection = Selection()
        selection.add("a")
        selection.add("b")
        assert selection.entity_id == "b"
        assert selection.is_primary("b")
        assert not selection.is_primary("a")

    def test_re_adding_moves_an_id_to_primary(self) -> None:
        """Not a no-op: the caller just said which one is last."""
        selection = Selection()
        selection.add("a")
        selection.add("b")
        selection.add("a")
        assert selection.entity_id == "a"
        assert selection.entity_ids == ("b", "a")

    def test_is_selected_is_true_for_non_primary_members(self) -> None:
        selection = Selection()
        selection.add("a")
        selection.add("b")
        assert selection.is_selected("a")

    def test_toggle_adds_then_removes(self) -> None:
        selection = Selection()
        selection.toggle("a")
        assert selection.is_selected("a")
        selection.toggle("a")
        assert not selection.is_selected("a")

    def test_remove_ignores_unknown_ids(self) -> None:
        selection = Selection()
        selection.add("a")
        selection.remove("nope")
        assert selection.entity_ids == ("a",)

    def test_select_many_collapses_duplicates_keeping_the_last(self) -> None:
        selection = Selection()
        selection.select_many(("a", "b", "a"))
        assert selection.entity_ids == ("a", "b")
        assert selection.entity_id == "b"

    def test_select_many_replaces_the_whole_selection(self) -> None:
        """What a marquee drag does."""
        selection = Selection()
        selection.select_many(("a", "b"))
        selection.select_many(("c",))
        assert selection.entity_ids == ("c",)

    def test_container_protocol(self) -> None:
        selection = Selection()
        selection.select_many(("a", "b"))
        assert "a" in selection
        assert "z" not in selection
        assert list(selection) == ["a", "b"]
        assert len(selection) == 2

    def test_iteration_snapshots_so_a_listener_may_mutate(self) -> None:
        """Iterating while a listener clears the selection must not raise."""
        selection = Selection()
        selection.select_many(("a", "b", "c"))
        seen = []
        for entity_id in selection:
            seen.append(entity_id)
            selection.clear()
        assert seen == ["a", "b", "c"]


class TestListeners:
    """Change notification."""

    def test_listeners_get_the_new_primary(self) -> None:
        selection = Selection()
        seen: list[str | None] = []
        selection.subscribe(seen.append)
        selection.select("hero")
        assert seen == ["hero"]

    def test_no_notification_without_a_real_change(self) -> None:
        selection = Selection()
        seen: list[str | None] = []
        selection.subscribe(seen.append)
        selection.select("hero")
        selection.select("hero")
        assert seen == ["hero"]

    def test_clearing_an_empty_selection_is_silent(self) -> None:
        selection = Selection()
        seen: list[str | None] = []
        selection.subscribe(seen.append)
        selection.clear()
        assert seen == []

    def test_adding_a_second_id_notifies_even_though_it_is_a_change(self) -> None:
        """The set changed, so listeners hear about it."""
        selection = Selection()
        seen: list[str | None] = []
        selection.select("a")
        selection.subscribe(seen.append)
        selection.add("b")
        assert seen == ["b"]

    def test_removing_the_primary_reports_the_new_one(self) -> None:
        selection = Selection()
        selection.select_many(("a", "b"))
        seen: list[str | None] = []
        selection.subscribe(seen.append)
        selection.remove("b")
        assert seen == ["a"]

    def test_unsubscribe_stops_notifications(self) -> None:
        selection = Selection()
        seen: list[str | None] = []
        selection.subscribe(seen.append)
        selection.unsubscribe(seen.append)
        selection.select("hero")
        assert seen == []

    def test_a_listener_may_unsubscribe_from_inside_the_callback(self) -> None:
        """Listeners are notified over a copy of the list."""
        selection = Selection()
        calls: list[str | None] = []

        def once(entity_id: str | None) -> None:
            calls.append(entity_id)
            selection.unsubscribe(once)

        selection.subscribe(once)
        selection.select("a")
        selection.select("b")
        assert calls == ["a"]
