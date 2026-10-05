"""The Hierarchy and Inspector panels, run as real ImGui frames.

No GL anywhere: ImGui's core builds frames without it, so these drive the
panels over a real `EntityManager` and assert on what they did.

Where a test needs a widget to report an *edit*, it patches that one widget
function to claim a change. That is a deliberate seam, not a mock of the
unit under test: driving a real drag-float would mean synthesising pixel
drags against font metrics, while the behaviour actually worth pinning is
this module's -- does an accepted edit write through, and does anything
mirroring the component get told. Both were bugs in the editor that was
deleted:

- `_draw_dataclass` called `setattr` unconditionally, so any `frozen=True`
  component raised `FrozenInstanceError`.
- Mutations went straight onto the component, with nothing notified, so
  physics bodies and render batches kept stale data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from pyguara.common.types import Color, Vector2
from pyguara.ecs.component import BaseComponent
from pyguara.ecs.manager import EntityManager
from pyguara.editor.panels.base import PanelContext
from pyguara.editor.panels.hierarchy import HierarchyPanel
from pyguara.editor.panels.inspector import InspectorPanel
from pyguara.editor.selection import Selection

imgui_bundle = pytest.importorskip("imgui_bundle")
imgui = imgui_bundle.imgui


@dataclass
class Spec(BaseComponent):
    """A mutable component covering every editable field type."""

    flag: bool = True
    count: int = 3
    speed: float = 1.5
    name: str = "hero"
    position: Vector2 = field(default_factory=lambda: Vector2(10.0, 20.0))
    tint: Color = field(default_factory=lambda: Color(255, 128, 0, 255))


@dataclass(frozen=True)
class Locked(BaseComponent):
    """A frozen component: assignment to its fields raises.

    The lifecycle hooks are overridden because `BaseComponent.on_attach`
    binds the owner with `self.entity = entity`, which a frozen dataclass
    rejects -- so a frozen component is only attachable if it opts out of
    that bind. (`on_attach` / `on_detach` are allowed lifecycle methods,
    not the logic methods `BaseComponent` forbids.)
    """

    value: float = 2.0

    def on_attach(self, entity: Any) -> None:
        """Skip the owner bind a frozen component cannot accept."""

    def on_detach(self) -> None:
        """Nothing to unbind."""


@dataclass
class Opaque(BaseComponent):
    """A component whose field has no editor."""

    payload: dict[str, int] = field(default_factory=dict)


def _draw(panel: Any, context: PanelContext, frames: int = 2) -> Any:
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


@pytest.fixture
def world() -> EntityManager:
    """A world with a two-level hierarchy and a detached sibling."""
    manager = EntityManager()
    manager.create_entity("root")
    manager.create_entity("child-a")
    manager.create_entity("child-b")
    manager.create_entity("grandchild")
    manager.create_entity("loner")
    manager.set_parent("child-a", "root")
    manager.set_parent("child-b", "root")
    manager.set_parent("grandchild", "child-a")
    return manager


@pytest.fixture
def selection() -> Selection:
    return Selection()


@pytest.mark.unit
class TestHierarchyPanel:
    def test_it_draws_a_populated_world(
        self, imgui_ctx: Any, world: EntityManager, selection: Selection
    ) -> None:
        draw_data = _draw(
            HierarchyPanel(), PanelContext(entity_manager=world, selection=selection)
        )
        assert draw_data.total_vtx_count > 0

    def test_a_world_with_entities_draws_more_than_an_empty_one(
        self, imgui_ctx: Any, world: EntityManager, selection: Selection
    ) -> None:
        """Guards the "renders but shows nothing" failure: the tree has to
        actually put the entities on screen, not just open a window."""
        populated = _draw(
            HierarchyPanel(), PanelContext(entity_manager=world, selection=selection)
        ).total_vtx_count
        empty = _draw(
            HierarchyPanel(),
            PanelContext(entity_manager=EntityManager(), selection=selection),
        ).total_vtx_count
        assert populated > empty

    def test_no_active_scene_is_not_an_empty_scene(
        self, imgui_ctx: Any, selection: Selection
    ) -> None:
        """`entity_manager=None` means no scene is active yet, which the
        panel must distinguish from an empty world -- the reason this layer
        does not substitute a throwaway manager the way `tools/base.py`
        does."""
        draw_data = _draw(
            HierarchyPanel(),
            PanelContext(entity_manager=None, selection=selection),
        )
        assert draw_data.total_vtx_count > 0  # drew the explanatory line

    def test_clicking_a_node_selects_that_entity(
        self,
        imgui_ctx: Any,
        world: EntityManager,
        selection: Selection,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The click -> selection wiring, with ImGui's hit test stubbed to
        report a click on the first node drawn."""
        clicks = iter([True])
        monkeypatch.setattr(
            imgui, "is_item_clicked", lambda *a, **k: next(clicks, False)
        )
        monkeypatch.setattr(imgui, "is_item_toggled_open", lambda *a, **k: False)

        _draw(
            HierarchyPanel(),
            PanelContext(entity_manager=world, selection=selection),
            frames=1,
        )
        # Roots are sorted, so "loner" precedes "root".
        assert selection.entity_id == "loner"

    def test_clicking_the_open_arrow_does_not_select(
        self,
        imgui_ctx: Any,
        world: EntityManager,
        selection: Selection,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Expanding a node and selecting it are different gestures."""
        monkeypatch.setattr(imgui, "is_item_clicked", lambda *a, **k: True)
        monkeypatch.setattr(imgui, "is_item_toggled_open", lambda *a, **k: True)

        _draw(
            HierarchyPanel(),
            PanelContext(entity_manager=world, selection=selection),
            frames=1,
        )
        assert selection.entity_id is None

    def test_a_deep_chain_does_not_blow_the_stack(
        self, imgui_ctx: Any, selection: Selection, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A chain past the depth cap stops rather than recursing until
        Python's own limit takes the window with it."""
        manager = EntityManager()
        manager.create_entity("e0")
        for index in range(1, 200):
            manager.create_entity(f"e{index}")
            manager.set_parent(f"e{index}", f"e{index - 1}")

        # Force every node open so the recursion actually descends -- by
        # adding `default_open` to the real call, not by replacing it: a
        # stub that returns True without pushing an ID makes the panel's
        # matching `tree_pop()` underflow ImGui's ID stack, which is a bug
        # in the stub rather than in the panel.
        real_tree_node_ex = imgui.tree_node_ex
        monkeypatch.setattr(
            imgui,
            "tree_node_ex",
            lambda label, flags=0: real_tree_node_ex(
                label, flags | imgui.TreeNodeFlags_.default_open.value
            ),
        )

        draw_data = _draw(
            HierarchyPanel(),
            PanelContext(entity_manager=manager, selection=selection),
            frames=1,
        )
        assert draw_data is not None  # completed instead of recursing away

    def test_an_entity_removed_mid_frame_is_skipped(
        self, imgui_ctx: Any, world: EntityManager, selection: Selection
    ) -> None:
        world.remove_entity("loner")
        world.flush_pending_removals()
        _draw(HierarchyPanel(), PanelContext(entity_manager=world, selection=selection))


@pytest.mark.unit
class TestInspectorPanel:
    def test_nothing_selected_still_draws(
        self, imgui_ctx: Any, world: EntityManager, selection: Selection
    ) -> None:
        draw_data = _draw(
            InspectorPanel(), PanelContext(entity_manager=world, selection=selection)
        )
        assert draw_data.total_vtx_count > 0

    def test_a_destroyed_selection_is_reported(
        self, imgui_ctx: Any, world: EntityManager, selection: Selection
    ) -> None:
        """Selected, then destroyed. Saying so beats an empty panel that
        looks identical to "selected something with no components"."""
        selection.select("root")
        world.remove_entity("root")
        world.flush_pending_removals()
        _draw(InspectorPanel(), PanelContext(entity_manager=world, selection=selection))

    def test_it_draws_the_selected_entity_components(
        self, imgui_ctx: Any, world: EntityManager, selection: Selection
    ) -> None:
        entity = world.get_entity("root")
        assert entity is not None
        entity.add_component(Spec())
        selection.select("root")

        draw_data = _draw(
            InspectorPanel(), PanelContext(entity_manager=world, selection=selection)
        )
        assert draw_data.total_vtx_count > 0

    @pytest.mark.parametrize(
        ("widget", "reported", "attribute", "expected"),
        [
            ("checkbox", False, "flag", False),
            ("input_int", 42, "count", 42),
            ("drag_float", 9.5, "speed", 9.5),
            ("input_text", "villain", "name", "villain"),
        ],
    )
    def test_an_accepted_edit_writes_through(
        self,
        imgui_ctx: Any,
        world: EntityManager,
        selection: Selection,
        monkeypatch: pytest.MonkeyPatch,
        widget: str,
        reported: Any,
        attribute: str,
        expected: Any,
    ) -> None:
        entity = world.get_entity("root")
        assert entity is not None
        entity.add_component(Spec())
        selection.select("root")

        monkeypatch.setattr(imgui, "collapsing_header", lambda *a, **k: True)
        monkeypatch.setattr(imgui, widget, lambda *a, **k: (True, reported))

        _draw(
            InspectorPanel(),
            PanelContext(entity_manager=world, selection=selection),
            frames=1,
        )
        assert getattr(entity.get_component(Spec), attribute) == expected

    def test_an_accepted_edit_notifies_the_manager(
        self,
        imgui_ctx: Any,
        world: EntityManager,
        selection: Selection,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The old editor mutated components with nothing notified, so
        anything mirroring them -- physics bodies, render batches, the
        spatial index -- kept stale data."""
        entity = world.get_entity("root")
        assert entity is not None
        entity.add_component(Spec())
        selection.select("root")

        changed: list[str] = []
        world.subscribe_component_changed(Spec, lambda e, _c: changed.append(e.id))

        monkeypatch.setattr(imgui, "collapsing_header", lambda *a, **k: True)
        monkeypatch.setattr(imgui, "drag_float", lambda *a, **k: (True, 7.0))

        _draw(
            InspectorPanel(),
            PanelContext(entity_manager=world, selection=selection),
            frames=1,
        )
        assert changed == ["root"]

    def test_an_unchanged_field_notifies_nothing(
        self,
        imgui_ctx: Any,
        world: EntityManager,
        selection: Selection,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entity = world.get_entity("root")
        assert entity is not None
        entity.add_component(Spec())
        selection.select("root")

        changed: list[str] = []
        world.subscribe_component_changed(Spec, lambda e, _c: changed.append(e.id))
        monkeypatch.setattr(imgui, "collapsing_header", lambda *a, **k: True)

        _draw(
            InspectorPanel(),
            PanelContext(entity_manager=world, selection=selection),
            frames=1,
        )
        assert changed == []

    def test_a_vector2_edit_replaces_the_whole_value(
        self,
        imgui_ctx: Any,
        world: EntityManager,
        selection: Selection,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Vector2 subclasses pymunk's immutable Vec2d, so an edit cannot
        assign to .x/.y -- it has to build a new one."""
        entity = world.get_entity("root")
        assert entity is not None
        entity.add_component(Spec())
        selection.select("root")

        monkeypatch.setattr(imgui, "collapsing_header", lambda *a, **k: True)
        monkeypatch.setattr(imgui, "drag_float2", lambda *a, **k: (True, [4.0, 5.0]))

        _draw(
            InspectorPanel(),
            PanelContext(entity_manager=world, selection=selection),
            frames=1,
        )
        position = entity.get_component(Spec).position
        assert (position.x, position.y) == (4.0, 5.0)
        assert isinstance(position, Vector2)

    def test_a_colour_edit_round_trips_through_0_255(
        self,
        imgui_ctx: Any,
        world: EntityManager,
        selection: Selection,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """ImGui edits colour as 0..1 floats; `Color` stores 0..255 ints."""
        entity = world.get_entity("root")
        assert entity is not None
        entity.add_component(Spec())
        selection.select("root")

        monkeypatch.setattr(imgui, "collapsing_header", lambda *a, **k: True)
        monkeypatch.setattr(
            imgui, "color_edit4", lambda *a, **k: (True, [1.0, 0.0, 0.5, 1.0])
        )

        _draw(
            InspectorPanel(),
            PanelContext(entity_manager=world, selection=selection),
            frames=1,
        )
        tint = entity.get_component(Spec).tint
        assert (tint.r, tint.g, tint.b, tint.a) == (255, 0, 128, 255)

    def test_a_frozen_component_is_never_assigned_to(
        self,
        imgui_ctx: Any,
        world: EntityManager,
        selection: Selection,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The exact crash the previous editor shipped: `setattr` on a
        `frozen=True` dataclass raises `FrozenInstanceError`. Even with
        every widget claiming an edit, nothing may be written."""
        entity = world.get_entity("root")
        assert entity is not None
        entity.add_component(Locked())
        selection.select("root")

        monkeypatch.setattr(imgui, "collapsing_header", lambda *a, **k: True)
        monkeypatch.setattr(imgui, "drag_float", lambda *a, **k: (True, 99.0))

        _draw(
            InspectorPanel(),
            PanelContext(entity_manager=world, selection=selection),
            frames=1,
        )
        assert entity.get_component(Locked).value == 2.0

    def test_a_field_with_no_editor_is_left_alone(
        self,
        imgui_ctx: Any,
        world: EntityManager,
        selection: Selection,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        entity = world.get_entity("root")
        assert entity is not None
        entity.add_component(Opaque(payload={"a": 1}))
        selection.select("root")

        monkeypatch.setattr(imgui, "collapsing_header", lambda *a, **k: True)

        _draw(
            InspectorPanel(),
            PanelContext(entity_manager=world, selection=selection),
            frames=1,
        )
        assert entity.get_component(Opaque).payload == {"a": 1}

    def test_an_entity_with_no_components_draws(
        self, imgui_ctx: Any, world: EntityManager, selection: Selection
    ) -> None:
        selection.select("loner")
        _draw(InspectorPanel(), PanelContext(entity_manager=world, selection=selection))
