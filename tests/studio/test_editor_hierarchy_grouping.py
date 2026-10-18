"""Filtering and grouping in the Hierarchy panel.

A generated level arrives as hundreds of flat siblings -- `tile_0_0`
through `tile_19_11` -- because an ECS scene has none of the pressure a
Godot scene has to hang them off a parent. Listing them one per row is
unreadable: the demo this was reported from put 252 rows in the panel, of
which 232 were tiles.

Two answers, both from Godot's Scene dock: a filter box, and folding runs
of same-prefix siblings into one row. The folding is display only -- no
entity is named `tile` and nothing is reparented -- which the tests below
pin as carefully as the folding itself, because a row that looked like a
parent and was not would be worse than the list it replaced.
"""

from __future__ import annotations

from typing import Any

import pytest

from pyguara.ecs.manager import EntityManager

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.studio.panels.base import PanelContext  # noqa: E402
from pyguara.studio.panels.hierarchy import (  # noqa: E402
    GROUP_THRESHOLD,
    HierarchyPanel,
    group_key,
    group_siblings,
)
from pyguara.studio.selection import Selection  # noqa: E402


@pytest.fixture
def level() -> EntityManager:
    """A world shaped like a generated level: a few named, many numbered."""
    manager = EntityManager()
    for name in ("player", "falcao", "goal", "sun", "moving_platform"):
        manager.create_entity(name)
    for index in range(12):
        manager.create_entity(f"tile_0_{index}")
    for index in range(7):
        manager.create_entity(f"solid_{index}")
    for index in range(2):
        manager.create_entity(f"collectible_{index}_4")
    return manager


def _draw(panel: HierarchyPanel, context: PanelContext, frames: int = 2) -> Any:
    """Draw `panel` for `frames` complete ImGui frames.

    Two by default: ImGui emits no geometry on the very first frame of a
    context, so a single-frame assertion on vertex counts would pass or
    fail for the wrong reason.

    Args:
        panel: The panel to draw.
        context: The panel context to pass it.
        frames: How many frames to run.

    Returns:
        The final frame's draw data.
    """
    draw_data = None
    for _ in range(frames):
        imgui.new_frame()
        panel.draw(context)
        imgui.render()
        draw_data = imgui.get_draw_data()
    return draw_data


@pytest.mark.unit
class TestTheGroupKey:
    @pytest.mark.parametrize(
        ("entity_id", "expected"),
        [
            ("tile_0_0", "tile"),
            ("tile_19_11", "tile"),
            ("collectible_18_10", "collectible"),
            ("solid_3", "solid"),
            ("moving_platform", "moving_platform"),
            ("player", "player"),
            ("hazard_33_19", "hazard"),
        ],
    )
    def test_it_stops_at_the_first_number(self, entity_id: str, expected: str) -> None:
        """A generated name is a prefix and coordinates, which is what
        makes the prefix a reliable stand-in for the parent the scene does
        not have."""
        assert group_key(entity_id) == expected

    def test_a_name_with_no_numbers_is_its_own_key(self) -> None:
        """So it groups with nothing and stays where it was."""
        assert group_key("player") == "player"

    def test_an_all_numeric_name_has_no_key(self) -> None:
        assert group_key("42") == ""
        assert group_key("0_0") == ""

    def test_grouping_keeps_the_order_it_was_given(self) -> None:
        groups = group_siblings(["a_1", "b_1", "a_2"])
        assert list(groups) == ["a", "b"]
        assert groups["a"] == ["a_1", "a_2"]


@pytest.mark.unit
class TestFolding:
    def test_a_long_run_collapses_to_one_row(
        self, imgui_ctx: Any, level: EntityManager
    ) -> None:
        """Twelve tiles behind one row, which is the whole point."""
        panel = HierarchyPanel()
        context = PanelContext(entity_manager=level, selection=Selection())

        folded = _draw(panel, context).total_vtx_count

        panel.set_filter("tile")
        opened = _draw(panel, context).total_vtx_count

        assert opened > folded, (
            "the tiles were not actually folded away; filtering to them "
            "should put more on screen, not less"
        )

    def test_a_short_run_stays_in_place(self) -> None:
        """Three stragglers read better where they are than behind a row
        that has to be opened to see them."""
        short = [f"crate_{index}" for index in range(GROUP_THRESHOLD - 1)]
        groups = group_siblings(short)
        assert len(groups["crate"]) < GROUP_THRESHOLD

    def test_nothing_is_reparented(self, imgui_ctx: Any, level: EntityManager) -> None:
        """The grouping is drawn, not applied. A row that looked like a
        parent but was not would be a worse lie than the long list."""
        panel = HierarchyPanel()
        before = sorted(e.id for e in level.get_all_entities())

        _draw(panel, PanelContext(entity_manager=level, selection=Selection()))

        assert sorted(e.id for e in level.get_all_entities()) == before
        assert level.get_entity("tile") is None, "a group became an entity"
        for entity in level.get_all_entities():
            assert level.parent_of(entity.id) is None


@pytest.mark.unit
class TestFiltering:
    def test_it_narrows_the_list(self, imgui_ctx: Any, level: EntityManager) -> None:
        panel = HierarchyPanel()
        context = PanelContext(entity_manager=level, selection=Selection())
        everything = _draw(panel, context).total_vtx_count

        panel.set_filter("player")
        narrowed = _draw(panel, context).total_vtx_count

        assert narrowed < everything

    def test_it_ignores_case(self) -> None:
        """Asserted on the predicate rather than on pixels: two draws of
        the same list can differ by a group left open from the draw
        before, which is correct and says nothing about matching."""
        panel = HierarchyPanel()
        panel.set_filter("PLAYER")
        assert panel._matches("player") is True
        panel.set_filter("player")
        assert panel._matches("PLAYER") is True
        panel.set_filter("tile")
        assert panel._matches("player") is False

    def test_a_filter_matching_nothing_says_so(
        self, imgui_ctx: Any, level: EntityManager
    ) -> None:
        """Rather than an empty panel, which reads as a broken one."""
        panel = HierarchyPanel()
        panel.set_filter("zzzzzz")
        context = PanelContext(entity_manager=level, selection=Selection())

        empty = _draw(panel, context).total_vtx_count

        panel.set_filter("")
        assert empty < _draw(panel, context).total_vtx_count
        assert empty > 0, "the panel drew nothing at all"

    def test_clearing_restores_everything(
        self, imgui_ctx: Any, level: EntityManager
    ) -> None:
        """At least everything: a group the filter forced open stays open
        afterwards, which is what a person who was just looking inside it
        expects."""
        panel = HierarchyPanel()
        context = PanelContext(entity_manager=level, selection=Selection())
        everything = _draw(panel, context).total_vtx_count

        panel.set_filter("player")
        narrowed = _draw(panel, context).total_vtx_count
        panel.set_filter("")
        restored = _draw(panel, context).total_vtx_count

        assert narrowed < everything
        assert restored >= everything


@pytest.mark.unit
class TestRevealingTheSelection:
    def test_a_selection_made_elsewhere_is_noticed(
        self, imgui_ctx: Any, level: EntityManager
    ) -> None:
        """Clicking an entity in the viewport has to scroll this panel to
        it, or the editor claims nothing is selected while the row sits
        two hundred rows below the fold."""
        panel = HierarchyPanel()
        selection = Selection()
        context = PanelContext(entity_manager=level, selection=selection)
        _draw(panel, context)

        selection.select("tile_0_7")
        _draw(panel, context)

        assert panel._last_selected == "tile_0_7"

    def test_a_group_holding_the_selection_opens(
        self, imgui_ctx: Any, level: EntityManager
    ) -> None:
        """Scrolling to a row inside a closed group would scroll to
        nothing."""
        panel = HierarchyPanel()
        selection = Selection()
        context = PanelContext(entity_manager=level, selection=selection)
        folded = _draw(panel, context).total_vtx_count

        selection.select("tile_0_7")
        revealed = _draw(panel, context).total_vtx_count

        assert revealed > folded

    def test_the_same_selection_twice_is_not_revealed_again(
        self, imgui_ctx: Any, level: EntityManager
    ) -> None:
        """Scrolling on every frame would fight a developer trying to
        scroll anywhere else."""
        panel = HierarchyPanel()
        selection = Selection()
        selection.select("player")
        context = PanelContext(entity_manager=level, selection=selection)

        _draw(panel, context)
        _draw(panel, context)

        assert panel._reveal is None
