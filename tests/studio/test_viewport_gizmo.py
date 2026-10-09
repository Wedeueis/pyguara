"""The transform gizmo, dragged for real through ImGui frames.

The requirement every test here circles is **one drag, one undo entry,
spanning the whole drag**. That is why the gizmo does not emit a command
per frame, and why on release it puts the starting values back before
applying a command: a command captures its inverse when applied, so one
applied against a world already holding the final values would record
"from final to final" and undo would restore nothing.

`pyguara/tools/gizmos.py` has no drag state, no handle hit-test and no
write-back to a `Transform` anywhere in it, so none of this is regression
cover -- it is the contract being established.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import Any

import pytest

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.common.components import Transform  # noqa: E402
from pyguara.common.types import Vector2  # noqa: E402
from pyguara.ecs.manager import EntityManager  # noqa: E402
from pyguara.editor.panels.base import PanelContext  # noqa: E402
from pyguara.editor.selection import Selection  # noqa: E402
from pyguara.graphics.components.camera import Camera2D  # noqa: E402
from pyguara.studio.session import StudioSession  # noqa: E402
from pyguara.studio.viewport.gizmo import (  # noqa: E402
    AXIS_LENGTH,
    ROTATION_SNAP_DEGREES,
    Axis,
    GizmoMode,
    TransformGizmo,
)
from pyguara.studio.viewport.panel import ViewportPanel  # noqa: E402
from pyguara.studio.viewport.picking import world_to_panel  # noqa: E402


class Harness:
    """A viewport with a gizmo, driveable a frame at a time."""

    def __init__(self, world: EntityManager, session: StudioSession) -> None:
        self.world = world
        self.session = session
        self.camera = Camera2D(800, 600)
        self.gizmo = TransformGizmo(session)
        self.selection = Selection()
        self.panel = ViewportPanel(
            camera_provider=lambda: self.camera,
            texture_provider=lambda: (1, 800, 600),
            overlays=[self.gizmo],
        )
        self.context = PanelContext(entity_manager=world, selection=self.selection)

    def frame(
        self,
        *,
        mouse: tuple[float, float] | None = None,
        down: bool | None = None,
        key: Any = None,
    ) -> None:
        """Run one frame, optionally with an input event."""
        io = imgui.get_io()
        if mouse is not None:
            io.add_mouse_pos_event(mouse[0], mouse[1])
        if down is not None:
            io.add_mouse_button_event(0, down)
        if key is not None:
            io.add_key_event(key, True)

        imgui.new_frame()
        imgui.set_next_window_pos(imgui.ImVec2(0, 0))
        imgui.set_next_window_size(imgui.ImVec2(640, 480))
        self.panel.draw(self.context)
        imgui.render()

        if key is not None:
            io.add_key_event(key, False)

    def settle(self) -> None:
        """Run enough frames for the panel to have a content region."""
        for _ in range(3):
            self.frame(mouse=(320, 260))

    def transform(self, entity_id: str) -> Transform:
        """Return an entity's transform."""
        entity = self.world.get_entity(entity_id)
        assert entity is not None
        return entity.get_component(Transform)

    def position(self, entity_id: str) -> Vector2:
        """Return an entity's position."""
        return self.transform(entity_id).position

    def screen(self, world_point: Vector2) -> tuple[float, float]:
        """Map a world position to a window position."""
        point = world_to_panel(
            self.camera,
            world_point,
            self.panel.state.content,
            self.panel.state.target,
        )
        content = self.panel.state.content
        return (point.x + content.x, point.y + content.y)

    def handle(self, entity_id: str, axis: Axis = Axis.BOTH) -> tuple[float, float]:
        """Return a handle's window position for the current mode."""
        pivot = self.screen(self.position(entity_id))
        if axis is Axis.X:
            return (pivot[0] + AXIS_LENGTH, pivot[1])
        if axis is Axis.Y:
            return (pivot[0], pivot[1] - AXIS_LENGTH)
        return pivot

    def drag(
        self,
        start: tuple[float, float],
        delta: tuple[float, float],
        *,
        steps: int = 3,
        release: bool = True,
    ) -> None:
        """Press at `start`, move by `delta` over `steps`, then release."""
        self.frame(mouse=start)
        self.frame(mouse=start, down=True)
        for step in range(1, steps + 1):
            fraction = step / steps
            self.frame(
                mouse=(
                    start[0] + delta[0] * fraction,
                    start[1] + delta[1] * fraction,
                )
            )
        if release:
            self.frame(mouse=(start[0] + delta[0], start[1] + delta[1]), down=False)


@pytest.fixture
def gui() -> Iterator[None]:
    """An ImGui context with no renderer and no GL."""
    context = imgui.create_context()
    imgui.set_current_context(context)
    io = imgui.get_io()
    io.display_size = imgui.ImVec2(1280, 720)
    io.delta_time = 1.0 / 60.0
    io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
    io.set_ini_filename("")
    yield
    imgui.destroy_context(context)


@pytest.fixture
def harness(world: EntityManager, core_registry) -> Harness:
    """A world with two entities, and a gizmo over it."""
    world.create_entity("hero").add_component(Transform(position=Vector2(0, 0)))
    world.create_entity("mob").add_component(Transform(position=Vector2(96, 0)))
    session = StudioSession(world, component_registry=core_registry)
    return Harness(world, session)


class TestOneDragOneEntry:
    """The requirement the whole design is shaped around."""

    def test_a_drag_moves_the_entity(self, gui: None, harness: Harness) -> None:
        harness.selection.select("hero")
        harness.settle()

        harness.drag(harness.handle("hero"), (60, 0))

        assert harness.position("hero").x > 0

    def test_the_drag_adds_exactly_one_undo_entry(
        self, gui: None, harness: Harness
    ) -> None:
        """Not one per mouse-motion frame, which is what a command per
        frame would give."""
        harness.selection.select("hero")
        harness.settle()

        harness.drag(harness.handle("hero"), (60, 0), steps=6)

        assert len(harness.session.stack.undo_labels) == 1

    def test_nothing_is_undoable_mid_drag(self, gui: None, harness: Harness) -> None:
        """Live feedback writes components directly, with no history
        churn."""
        harness.selection.select("hero")
        harness.settle()

        harness.drag(harness.handle("hero"), (60, 0), release=False)

        assert harness.position("hero").x > 0
        assert harness.session.stack.can_undo is False
        harness.frame(down=False)

    def test_one_undo_returns_to_where_the_drag_began(
        self, gui: None, harness: Harness
    ) -> None:
        """Not to the previous frame of the drag. This is the assertion
        that fails if the command is applied without restoring first: it
        would capture "from final to final" and undo nothing."""
        harness.selection.select("hero")
        harness.settle()
        before = harness.position("hero")

        harness.drag(harness.handle("hero"), (60, 20), steps=8)
        assert harness.position("hero") != before

        harness.session.undo()
        assert harness.position("hero") == before

    def test_redo_returns_to_the_end_of_the_drag(
        self, gui: None, harness: Harness
    ) -> None:
        harness.selection.select("hero")
        harness.settle()

        harness.drag(harness.handle("hero"), (60, 0))
        after = harness.position("hero")

        harness.session.undo()
        harness.session.redo()
        assert harness.position("hero") == after

    def test_a_drag_that_moved_nothing_adds_no_entry(
        self, gui: None, harness: Harness
    ) -> None:
        """Clicking a handle without moving is not an edit."""
        harness.selection.select("hero")
        harness.settle()

        harness.drag(harness.handle("hero"), (0, 0), steps=1)

        assert harness.session.stack.can_undo is False

    def test_the_drag_is_journaled(self, gui: None, harness: Harness) -> None:
        harness.selection.select("hero")
        harness.settle()

        harness.drag(harness.handle("hero"), (60, 0))

        assert harness.session.journal.entries[-1].action == "translate"


class TestMultiSelectDrag:
    """Several entities, moved together, undone together."""

    def test_every_selected_entity_moves(self, gui: None, harness: Harness) -> None:
        harness.selection.select_many(("hero", "mob"))
        harness.settle()
        before = (harness.position("hero"), harness.position("mob"))

        harness.drag(harness.handle("mob"), (40, 20))

        assert harness.position("hero") != before[0]
        assert harness.position("mob") != before[1]

    def test_they_move_by_the_same_delta(self, gui: None, harness: Harness) -> None:
        """A multi-drag preserves the relative layout; it does not
        collapse everything onto the cursor."""
        harness.selection.select_many(("hero", "mob"))
        harness.settle()
        gap = harness.position("mob") - harness.position("hero")

        harness.drag(harness.handle("mob"), (40, 20))

        assert harness.position("mob") - harness.position("hero") == gap

    def test_it_is_one_undo_entry(self, gui: None, harness: Harness) -> None:
        """Undoing a third of a move is not a state the user was in."""
        harness.selection.select_many(("hero", "mob"))
        harness.settle()

        harness.drag(harness.handle("mob"), (40, 20))

        assert harness.session.stack.undo_labels == ("Move 2 entities",)

    def test_one_undo_restores_every_entity(self, gui: None, harness: Harness) -> None:
        harness.selection.select_many(("hero", "mob"))
        harness.settle()
        before = (harness.position("hero"), harness.position("mob"))

        harness.drag(harness.handle("mob"), (40, 20))
        harness.session.undo()

        assert (harness.position("hero"), harness.position("mob")) == before

    def test_an_entity_with_no_transform_is_skipped(
        self, gui: None, harness: Harness
    ) -> None:
        """Selecting a UI entity alongside two sprites should not fail
        the drag."""
        harness.world.create_entity("no_transform")
        harness.selection.select_many(("hero", "no_transform"))
        harness.settle()

        harness.drag(harness.handle("hero"), (40, 0))

        assert harness.position("hero").x > 0


class TestAxisConstraints:
    """Grabbing an arrow restricts the drag to its axis."""

    def test_the_x_handle_moves_only_x(self, gui: None, harness: Harness) -> None:
        harness.selection.select("hero")
        harness.settle()

        harness.drag(harness.handle("hero", Axis.X), (60, 60))

        assert harness.position("hero").x > 0
        assert harness.position("hero").y == 0

    def test_the_y_handle_moves_only_y(self, gui: None, harness: Harness) -> None:
        harness.selection.select("hero")
        harness.settle()

        harness.drag(harness.handle("hero", Axis.Y), (60, 60))

        assert harness.position("hero").x == 0
        assert harness.position("hero").y != 0

    def test_the_centre_handle_moves_both(self, gui: None, harness: Harness) -> None:
        harness.selection.select("hero")
        harness.settle()

        harness.drag(harness.handle("hero", Axis.BOTH), (60, 60))

        assert harness.position("hero").x > 0
        assert harness.position("hero").y > 0


class TestCancel:
    """Escape, and the other ways a drag ends badly."""

    def test_escape_restores_the_starting_position(
        self, gui: None, harness: Harness
    ) -> None:
        harness.selection.select("hero")
        harness.settle()
        before = harness.position("hero")
        start = harness.handle("hero")

        harness.frame(mouse=start)
        harness.frame(mouse=start, down=True)
        harness.frame(mouse=(start[0] + 70, start[1]))
        assert harness.position("hero") != before

        harness.frame(key=imgui.Key.escape)

        assert harness.position("hero") == before
        harness.frame(down=False)

    def test_escape_adds_no_undo_entry(self, gui: None, harness: Harness) -> None:
        """A mis-drag leaves neither a change nor an undo entry."""
        harness.selection.select("hero")
        harness.settle()
        start = harness.handle("hero")

        harness.frame(mouse=start)
        harness.frame(mouse=start, down=True)
        harness.frame(mouse=(start[0] + 70, start[1]))
        harness.frame(key=imgui.Key.escape)

        assert harness.session.stack.can_undo is False
        harness.frame(down=False)

    def test_changing_mode_mid_drag_cancels_it(
        self, gui: None, harness: Harness
    ) -> None:
        """Otherwise a translation would be applied as a rotation."""
        harness.selection.select("hero")
        harness.settle()
        before = harness.position("hero")
        start = harness.handle("hero")

        harness.frame(mouse=start)
        harness.frame(mouse=start, down=True)
        harness.frame(mouse=(start[0] + 70, start[1]))

        harness.gizmo.mode = GizmoMode.ROTATE

        assert harness.position("hero") == before
        assert harness.gizmo.dragging is False
        harness.frame(down=False)

    def test_clearing_the_selection_mid_drag_cancels_it(
        self, gui: None, harness: Harness
    ) -> None:
        harness.selection.select("hero")
        harness.settle()
        before = harness.position("hero")
        start = harness.handle("hero")

        harness.frame(mouse=start)
        harness.frame(mouse=start, down=True)
        harness.frame(mouse=(start[0] + 70, start[1]))

        harness.selection.clear()
        harness.frame()

        assert harness.position("hero") == before
        harness.frame(down=False)

    def test_cancel_is_safe_with_no_drag(self, gui: None, harness: Harness) -> None:
        harness.gizmo.cancel()


class TestSnapping:
    """Grid snapping, in absolute world space."""

    def test_a_snapped_drag_lands_on_the_grid(
        self, gui: None, harness: Harness
    ) -> None:
        harness.world.get_entity("hero").get_component(Transform).position = Vector2(
            5, 5
        )
        harness.selection.select("hero")
        harness.settle()
        harness.panel.state.snap = True
        harness.panel.state.grid_size = 32.0

        harness.drag(harness.handle("hero"), (37, 7))

        position = harness.position("hero")
        assert position.x % 32 == 0
        assert position.y % 32 == 0

    def test_snapping_is_absolute_not_relative(
        self, gui: None, harness: Harness
    ) -> None:
        """Snapping the delta instead would leave an entity that began
        off-grid off it for ever, which is never what dragging onto a grid
        means."""
        harness.world.get_entity("hero").get_component(Transform).position = Vector2(
            7, 7
        )
        harness.selection.select("hero")
        harness.settle()
        harness.panel.state.snap = True
        harness.panel.state.grid_size = 32.0

        harness.drag(harness.handle("hero"), (50, 50))

        assert harness.position("hero").x % 32 == 0

    def test_snapping_off_leaves_a_free_position(
        self, gui: None, harness: Harness
    ) -> None:
        harness.selection.select("hero")
        harness.settle()
        harness.panel.state.snap = False

        harness.drag(harness.handle("hero"), (37, 0))

        assert harness.position("hero").x % 32 != 0


class TestRotate:
    """Rotation about the pivot."""

    def test_dragging_the_ring_rotates(self, gui: None, harness: Harness) -> None:
        harness.selection.select("hero")
        harness.settle()
        harness.gizmo.mode = GizmoMode.ROTATE
        harness.frame()

        from pyguara.studio.viewport.gizmo import ROTATE_RADIUS

        pivot = harness.screen(harness.position("hero"))
        handle = (pivot[0] + ROTATE_RADIUS, pivot[1])
        harness.drag(handle, (-40, -40))

        assert harness.transform("hero").rotation != 0.0

    def test_rotation_does_not_move_the_entity(
        self, gui: None, harness: Harness
    ) -> None:
        harness.selection.select("hero")
        harness.settle()
        harness.gizmo.mode = GizmoMode.ROTATE
        harness.frame()
        before = harness.position("hero")

        from pyguara.studio.viewport.gizmo import ROTATE_RADIUS

        pivot = harness.screen(before)
        harness.drag((pivot[0] + ROTATE_RADIUS, pivot[1]), (-40, -40))

        assert harness.position("hero") == before

    def test_a_rotation_is_one_undo_entry(self, gui: None, harness: Harness) -> None:
        harness.selection.select("hero")
        harness.settle()
        harness.gizmo.mode = GizmoMode.ROTATE
        harness.frame()

        from pyguara.studio.viewport.gizmo import ROTATE_RADIUS

        pivot = harness.screen(harness.position("hero"))
        harness.drag((pivot[0] + ROTATE_RADIUS, pivot[1]), (-40, -40), steps=6)

        assert len(harness.session.stack.undo_labels) == 1

    def test_snapped_rotation_lands_on_a_step(
        self, gui: None, harness: Harness
    ) -> None:
        """Degrees, not the grid size: a grid is a distance and means
        nothing to an angle."""
        harness.selection.select("hero")
        harness.settle()
        harness.gizmo.mode = GizmoMode.ROTATE
        harness.frame()
        harness.panel.state.snap = True

        from pyguara.studio.viewport.gizmo import ROTATE_RADIUS

        pivot = harness.screen(harness.position("hero"))
        harness.drag((pivot[0] + ROTATE_RADIUS, pivot[1]), (-30, -30))

        step = math.radians(ROTATION_SNAP_DEGREES)
        rotation = harness.transform("hero").rotation
        assert abs((rotation / step) - round(rotation / step)) < 1e-6


class TestScale:
    """Scaling about the pivot."""

    def test_dragging_outwards_scales_up(self, gui: None, harness: Harness) -> None:
        harness.selection.select("hero")
        harness.settle()
        harness.gizmo.mode = GizmoMode.SCALE
        harness.frame()

        harness.drag(harness.handle("hero", Axis.X), (60, 0))

        assert harness.transform("hero").scale.x > 1.0

    def test_the_x_handle_scales_only_x(self, gui: None, harness: Harness) -> None:
        harness.selection.select("hero")
        harness.settle()
        harness.gizmo.mode = GizmoMode.SCALE
        harness.frame()

        harness.drag(harness.handle("hero", Axis.X), (60, 0))

        assert harness.transform("hero").scale.y == 1.0

    def test_scaling_does_not_move_the_entity(
        self, gui: None, harness: Harness
    ) -> None:
        harness.selection.select("hero")
        harness.settle()
        harness.gizmo.mode = GizmoMode.SCALE
        harness.frame()
        before = harness.position("hero")

        harness.drag(harness.handle("hero", Axis.X), (60, 0))

        assert harness.position("hero") == before

    def test_a_scale_is_one_undo_entry(self, gui: None, harness: Harness) -> None:
        harness.selection.select("hero")
        harness.settle()
        harness.gizmo.mode = GizmoMode.SCALE
        harness.frame()

        harness.drag(harness.handle("hero", Axis.X), (60, 0), steps=6)

        assert len(harness.session.stack.undo_labels) == 1


class TestModeKeys:
    """Q, W and E, as every other editor binds them."""

    @pytest.mark.parametrize(
        ("key", "expected"),
        [
            (imgui.Key.q, GizmoMode.TRANSLATE),
            (imgui.Key.w, GizmoMode.ROTATE),
            (imgui.Key.e, GizmoMode.SCALE),
        ],
    )
    def test_each_key_selects_its_mode(
        self, gui: None, harness: Harness, key: Any, expected: GizmoMode
    ) -> None:
        harness.selection.select("hero")
        harness.settle()

        harness.frame(key=key)

        assert harness.gizmo.mode is expected

    def test_mode_keys_are_ignored_while_typing(
        self, gui: None, harness: Harness
    ) -> None:
        """Typing a name into the Inspector must not silently change the
        gizmo.

        Driven by giving a real text field keyboard focus, which is what
        sets `want_capture_keyboard`. Assigning the flag directly does not
        work -- ImGui recomputes it in `new_frame()` from what actually
        has focus -- and a test that did so would pass while asserting
        nothing.
        """
        harness.selection.select("hero")
        harness.settle()
        harness.gizmo.mode = GizmoMode.TRANSLATE

        text = "name"
        for index in range(3):
            imgui.new_frame()
            imgui.begin("Typing")
            if index == 0:
                imgui.set_keyboard_focus_here()
            _, text = imgui.input_text("field", text)
            imgui.end()

            imgui.set_next_window_pos(imgui.ImVec2(0, 0))
            imgui.set_next_window_size(imgui.ImVec2(640, 480))
            if index == 2:
                assert imgui.get_io().want_capture_keyboard, (
                    "the text field never took focus, so this test would assert nothing"
                )
                io = imgui.get_io()
                io.add_key_event(imgui.Key.w, True)
            harness.panel.draw(harness.context)
            imgui.render()
            if index == 2:
                imgui.get_io().add_key_event(imgui.Key.w, False)

        assert harness.gizmo.mode is GizmoMode.TRANSLATE


class TestMouseOwnership:
    """The gizmo tells the viewport when it is using the mouse."""

    def test_it_consumes_the_mouse_while_dragging(
        self, gui: None, harness: Harness
    ) -> None:
        """What stops a gizmo drag from also starting a marquee, or
        re-picking whatever sits behind the handle."""
        harness.selection.select("hero")
        harness.settle()
        start = harness.handle("hero")

        harness.frame(mouse=start)
        harness.frame(mouse=start, down=True)

        assert harness.gizmo.dragging is True
        harness.frame(down=False)

    def test_the_selection_is_unchanged_by_grabbing_a_handle(
        self, gui: None, harness: Harness
    ) -> None:
        """Clicking the handle over `hero` must not re-pick whatever
        sprite is behind it."""
        harness.selection.select("hero")
        harness.settle()

        harness.drag(harness.handle("hero", Axis.X), (40, 0))

        assert harness.selection.entity_ids == ("hero",)

    def test_it_does_not_consume_the_mouse_when_idle(
        self, gui: None, harness: Harness
    ) -> None:
        harness.selection.select("hero")
        harness.settle()
        assert harness.gizmo.dragging is False


class TestDegenerateStates:
    """What the gizmo does when there is nothing to draw."""

    def test_no_selection_draws_nothing(self, gui: None, harness: Harness) -> None:
        harness.settle()
        assert harness.gizmo.dragging is False

    def test_a_selection_with_no_transform_draws_nothing(
        self, gui: None, harness: Harness
    ) -> None:
        harness.world.create_entity("bare")
        harness.selection.select("bare")
        harness.settle()
        assert harness.gizmo.dragging is False

    def test_a_destroyed_selection_mid_drag_is_survivable(
        self, gui: None, harness: Harness
    ) -> None:
        harness.selection.select("hero")
        harness.settle()
        start = harness.handle("hero")

        harness.frame(mouse=start)
        harness.frame(mouse=start, down=True)
        harness.world.remove_entity("hero")
        harness.world.flush_pending_removals()
        harness.frame(mouse=(start[0] + 40, start[1]))
        harness.frame(down=False)

    def test_no_scene_draws_nothing(self, gui: None, harness: Harness) -> None:
        harness.context = PanelContext(entity_manager=None, selection=harness.selection)
        harness.frame()
        assert harness.gizmo.dragging is False


class TestPivotChoice:
    """Which entity the gizmo anchors to."""

    def test_the_primary_selection_is_the_pivot(
        self, gui: None, harness: Harness
    ) -> None:
        """ "The last one I clicked" is what a user means by the anchor."""
        harness.selection.select_many(("hero", "mob"))
        harness.settle()

        # Dragging the handle over `mob` works; over `hero` it does not,
        # because the gizmo is drawn at the primary.
        harness.drag(harness.handle("mob"), (40, 0))
        assert harness.position("hero").x > 0

    def test_it_falls_back_when_the_primary_cannot_be_moved(
        self, gui: None, harness: Harness
    ) -> None:
        """A selection routinely mixes movable things with things that are
        not: a UI entity, a singleton holding game state, an empty used as
        a tag. Giving up because the last click landed on one of those
        would make the gizmo vanish for no visible reason."""
        harness.world.create_entity("game_state")
        harness.selection.select_many(("hero", "game_state"))
        harness.settle()

        harness.drag(harness.handle("hero"), (40, 0))

        assert harness.position("hero").x > 0

    def test_a_selection_of_nothing_movable_draws_nothing(
        self, gui: None, harness: Harness
    ) -> None:
        harness.world.create_entity("game_state")
        harness.selection.select("game_state")
        harness.settle()
        assert harness.gizmo.dragging is False
