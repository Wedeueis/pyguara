"""The transform gizmo: dragging an entity rather than typing at it.

`pyguara/tools/gizmos.py` draws arrows and a ring and that is all it
does. Its `process_event` switches mode on Q/W/E and click-selects; there
is no drag state, no handle hit-test, and no write-back to a `Transform`
anywhere in the file. In the configuration the sandbox actually registers
-- with a selection provider set -- even the click branch is disabled, so
it is a read-only indicator. The arrow geometry and the Q/W/E convention
are worth keeping. The manipulation is new.

**One drag is one undo entry, and the entry spans the whole drag.** That
is the requirement everything here is shaped around, and it is why the
drag does not emit a command per frame:

1. On drag begin, the starting transform of every selected entity is
   recorded.
2. While dragging, components are written **directly**, for live
   feedback with no history churn.
3. On release, the recorded starting values are put back and a single
   `CompositeCommand` is applied through the session.

Step 3 looks redundant and is not. A command captures its inverse when it
is applied, so applying it against a world already holding the final
values would record "from final to final" and undo would restore nothing.
Restoring first costs one frame of nothing visible and makes the history
correct.

Escape cancels: the recorded values go back and no command is applied, so
a mis-drag leaves neither a change nor an undo entry.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from imgui_bundle import imgui

from pyguara.common.components import Transform
from pyguara.common.types import Vector2
from pyguara.ecs.manager import EntityManager
from pyguara.editor.panels.base import PanelContext
from pyguara.graphics.components.camera import Camera2D
from pyguara.log import get_logger
from pyguara.studio.agent.journal import Actor
from pyguara.studio.commands.base import CompositeCommand, EditCommand, EditError
from pyguara.studio.commands.entity import SetField
from pyguara.studio.session import StudioSession
from pyguara.studio.viewport.panel import ViewportOverlay, ViewportState
from pyguara.studio.viewport.picking import screen_to_world, world_to_panel

logger = get_logger(__name__)

HANDLE_GRAB_RADIUS = 9.0
"""How close, in panel pixels, the cursor must be to grab a handle.

In pixels rather than world units deliberately: a handle is a screen-space
affordance, and one that shrank as you zoomed out would become
ungrabbable at exactly the point you most want to drag something a long
way.
"""

AXIS_LENGTH = 64.0
"""Arrow length in panel pixels."""

ARROW_HEAD = 11.0
"""Arrow head size in panel pixels."""

ROTATE_RADIUS = 52.0
"""Rotation ring radius in panel pixels."""

SCALE_HANDLE = 7.0
"""Half-side of a square scale handle, in panel pixels."""

ROTATION_SNAP_DEGREES = 15.0
"""Rotation step when snapping is on.

Degrees, not the grid size: a grid is a distance and means nothing to an
angle. Fifteen degrees is the common choice and divides the useful ones.
"""

SCALE_SNAP_STEP = 0.25
"""Scale step when snapping is on."""

_X_COLOUR = imgui.IM_COL32(255, 80, 80, 255)
_Y_COLOUR = imgui.IM_COL32(80, 255, 80, 255)
_BOTH_COLOUR = imgui.IM_COL32(255, 220, 90, 255)
_ROTATE_COLOUR = imgui.IM_COL32(110, 150, 255, 255)
_SCALE_COLOUR = imgui.IM_COL32(255, 200, 80, 255)
_HOVER_COLOUR = imgui.IM_COL32(255, 255, 255, 255)


class GizmoMode(Enum):
    """What the gizmo manipulates.

    Mirrors `pyguara/tools/gizmos.py`'s enum and its Q/W/E keys, which
    match every other editor and are therefore not worth differing on.
    """

    TRANSLATE = "translate"
    ROTATE = "rotate"
    SCALE = "scale"


class Axis(Enum):
    """Which axes a drag is constrained to."""

    X = "x"
    Y = "y"
    BOTH = "both"


@dataclass(frozen=True)
class _Handle:
    """One grabbable spot, in panel coordinates.

    Attributes:
        axis: What grabbing it constrains the drag to.
        position: Where it is, relative to the panel's content origin.
    """

    axis: Axis
    position: Vector2


@dataclass
class _DragState:
    """A drag in progress.

    Attributes:
        mode: What is being manipulated.
        axis: The constraint the grabbed handle imposes.
        origin: The world position the drag started from.
        start_values: Each entity's transform at drag start, as
            `(position, rotation, scale)`.
        pivot: The primary entity's starting position, which rotation and
            scale are measured about.
        start_angle: The cursor's angle about the pivot at drag start.
        start_distance: The cursor's distance from the pivot at drag start.
    """

    mode: GizmoMode
    axis: Axis
    origin: Vector2
    start_values: dict[str, tuple[Vector2, float, Vector2]] = field(
        default_factory=dict
    )
    pivot: Vector2 = field(default_factory=Vector2.zero)
    start_angle: float = 0.0
    start_distance: float = 1.0


class TransformGizmo(ViewportOverlay):
    """Translate, rotate and scale the selection by dragging."""

    def __init__(
        self,
        session: StudioSession,
        *,
        mode: GizmoMode = GizmoMode.TRANSLATE,
    ) -> None:
        """Initialize the gizmo.

        Args:
            session: Where completed drags are applied, so a drag is
                undoable and journaled like any other edit.
            mode: The mode to start in.
        """
        self._session = session
        self._mode = mode
        self._drag: _DragState | None = None
        self._hovered: Axis | None = None

    @property
    def mode(self) -> GizmoMode:
        """What the gizmo currently manipulates."""
        return self._mode

    @mode.setter
    def mode(self, mode: GizmoMode) -> None:
        """Change mode, abandoning any drag in progress.

        Switching mid-drag would apply a translation as a rotation.
        """
        if self._drag is not None:
            self.cancel()
        self._mode = mode

    @property
    def dragging(self) -> bool:
        """Whether a drag is in progress."""
        return self._drag is not None

    def cancel(self) -> None:
        """Abandon a drag, restoring every entity to where it started.

        No command is applied, so a mis-drag leaves neither a change nor
        an undo entry.
        """
        drag = self._drag
        self._drag = None
        if drag is None:
            return
        self._restore(drag)

    def draw(
        self,
        context: PanelContext,
        state: ViewportState,
        camera: Camera2D,
        draw_list: Any,
    ) -> bool:
        """Draw the handles and run the drag.

        Args:
            context: The world and selection.
            state: The viewport's geometry and snap settings.
            camera: The camera the frame was rendered with.
            draw_list: The panel's ImGui draw list.

        Returns:
            True while the gizmo is using the mouse, so the viewport does
            not also pick or marquee with it.
        """
        manager = context.entity_manager
        if manager is None or not state.has_geometry:
            return False

        self._handle_mode_keys()

        pivot_id = self._pivot_id(context, manager)
        if pivot_id is None:
            self.cancel()
            return False

        transform = self._transform_of(manager, pivot_id)
        if transform is None:  # pragma: no cover - _pivot_id checked it
            self.cancel()
            return False

        centre = self._to_panel(camera, state, transform.position)
        handles = self._handles(centre)

        if self._drag is not None:
            self._continue_drag(context, manager, state, camera)
        else:
            self._maybe_begin_drag(context, manager, state, camera, handles)

        self._draw_handles(draw_list, state, centre, handles)
        return self._drag is not None

    # ----------------------------------------------------------------
    # Input
    # ----------------------------------------------------------------

    def _handle_mode_keys(self) -> None:
        """Switch mode on Q, W or E.

        The same keys `pyguara/tools/gizmos.py` used, which match every
        other editor. Ignored while a text field has focus, or typing a
        name into the Inspector would silently change the gizmo.
        """
        if imgui.get_io().want_capture_keyboard:
            return
        if imgui.is_key_pressed(imgui.Key.q):
            self.mode = GizmoMode.TRANSLATE
        elif imgui.is_key_pressed(imgui.Key.w):
            self.mode = GizmoMode.ROTATE
        elif imgui.is_key_pressed(imgui.Key.e):
            self.mode = GizmoMode.SCALE

    def _maybe_begin_drag(
        self,
        context: PanelContext,
        manager: EntityManager,
        state: ViewportState,
        camera: Camera2D,
        handles: list[_Handle],
    ) -> None:
        """Start a drag if the cursor pressed on a handle.

        Args:
            context: The world and selection.
            manager: The world.
            state: The viewport's geometry.
            camera: The camera the frame was rendered with.
            handles: This frame's handles, in panel coordinates.
        """
        cursor = self._cursor_in_panel(state)
        self._hovered = self._handle_under(handles, cursor)

        if self._hovered is None or not imgui.is_mouse_clicked(imgui.MouseButton_.left):
            return

        pivot_id = self._pivot_id(context, manager)
        if pivot_id is None:  # pragma: no cover - checked by the caller
            return
        pivot_transform = self._transform_of(manager, pivot_id)
        if pivot_transform is None:  # pragma: no cover - checked by the caller
            return

        start_values: dict[str, tuple[Vector2, float, Vector2]] = {}
        for entity_id in context.selection.entity_ids:
            transform = self._transform_of(manager, entity_id)
            if transform is not None:
                start_values[entity_id] = (
                    transform.position,
                    transform.rotation,
                    transform.scale,
                )

        if not start_values:  # pragma: no cover - pivot is in the selection
            return

        origin = self._to_world(camera, state, cursor)
        pivot = pivot_transform.position
        offset = origin - pivot
        self._drag = _DragState(
            mode=self._mode,
            axis=self._hovered,
            origin=origin,
            start_values=start_values,
            pivot=pivot,
            start_angle=math.atan2(offset.y, offset.x),
            # Guarded away from zero: a drag beginning exactly on the
            # pivot would divide by it on the first scale frame.
            start_distance=max(offset.length, 1e-3),
        )

    def _continue_drag(
        self,
        context: PanelContext,
        manager: EntityManager,
        state: ViewportState,
        camera: Camera2D,
    ) -> None:
        """Advance, finish or cancel the drag.

        Args:
            context: The world and selection.
            manager: The world.
            state: The viewport's geometry and snap settings.
            camera: The camera the frame was rendered with.
        """
        drag = self._drag
        if drag is None:  # pragma: no cover - checked by the caller
            return

        if imgui.is_key_pressed(imgui.Key.escape):
            self.cancel()
            return

        cursor_world = self._to_world(camera, state, self._cursor_in_panel(state))
        self._apply_live(manager, drag, state, cursor_world)

        if imgui.is_mouse_down(imgui.MouseButton_.left):
            return

        self._drag = None
        self._commit(manager, drag, state, cursor_world)

    # ----------------------------------------------------------------
    # The drag itself
    # ----------------------------------------------------------------

    def _apply_live(
        self,
        manager: EntityManager,
        drag: _DragState,
        state: ViewportState,
        cursor_world: Vector2,
    ) -> None:
        """Write this frame's values straight onto the components.

        Direct assignment rather than a command: a command per frame would
        fill the history with a hundred entries for one gesture, and
        coalescing them afterwards cannot span the several entities a
        multi-selection drag touches.

        `notify_component_changed` is still called, because everything
        mirroring a transform -- physics bodies, the spatial index --
        needs to follow the drag rather than jump at the end of it.

        Args:
            manager: The world.
            drag: The drag in progress.
            state: The viewport's snap settings.
            cursor_world: Where the cursor is now, in world space.
        """
        for entity_id, values in drag.start_values.items():
            transform = self._transform_of(manager, entity_id)
            if transform is None:
                continue
            position, rotation, scale = self._value_for(
                drag, state, cursor_world, values
            )
            transform.position = position
            transform.rotation = rotation
            transform.scale = scale
            manager.notify_component_changed(entity_id, Transform)

    def _commit(
        self,
        manager: EntityManager,
        drag: _DragState,
        state: ViewportState,
        cursor_world: Vector2,
    ) -> None:
        """Put the starting values back, then apply the drag as one edit.

        The restore is what makes the history correct. A command captures
        its inverse when applied, so applying one against a world already
        holding the final values would record "from final to final" and
        undo would restore nothing. Restoring first costs one frame of
        nothing visible.

        Args:
            manager: The world.
            drag: The finished drag.
            state: The viewport's snap settings.
            cursor_world: Where the cursor ended, in world space.
        """
        commands: list[EditCommand] = []
        for entity_id, values in drag.start_values.items():
            transform = self._transform_of(manager, entity_id)
            if transform is None:
                continue

            position, rotation, scale = self._value_for(
                drag, state, cursor_world, values
            )
            start_position, start_rotation, start_scale = values

            transform.position = start_position
            transform.rotation = start_rotation
            transform.scale = start_scale

            if drag.mode is GizmoMode.TRANSLATE:
                if position != start_position:
                    commands.append(
                        SetField(entity_id, Transform, "position", position)
                    )
            elif drag.mode is GizmoMode.ROTATE:
                if rotation != start_rotation:
                    commands.append(
                        SetField(entity_id, Transform, "rotation", rotation)
                    )
            elif scale != start_scale:
                commands.append(SetField(entity_id, Transform, "scale", scale))

        if not commands:
            # A click on a handle that moved nothing. The restore above
            # already put the world back; the notification tells anything
            # mirroring a transform that the live drag has been undone.
            for entity_id in drag.start_values:
                manager.notify_component_changed(entity_id, Transform)
            return

        label = self._label(drag, len(commands))
        edit: EditCommand = (
            commands[0] if len(commands) == 1 else CompositeCommand(label, commands)
        )
        try:
            self._session.apply(edit, actor=Actor.HUMAN, action=drag.mode.value)
        except EditError as exc:
            # The world is already back at the starting values, so a
            # refused edit leaves the drag simply undone.
            logger.warning(f"Gizmo drag could not be applied: {exc}")

    def _value_for(
        self,
        drag: _DragState,
        state: ViewportState,
        cursor_world: Vector2,
        start: tuple[Vector2, float, Vector2],
    ) -> tuple[Vector2, float, Vector2]:
        """Return one entity's transform for the drag's current position.

        Args:
            drag: The drag in progress.
            state: The viewport's snap settings.
            cursor_world: Where the cursor is, in world space.
            start: The entity's `(position, rotation, scale)` at drag
                start.

        Returns:
            The new `(position, rotation, scale)`.
        """
        start_position, start_rotation, start_scale = start

        if drag.mode is GizmoMode.TRANSLATE:
            delta = cursor_world - drag.origin
            if drag.axis is Axis.X:
                delta = Vector2(delta.x, 0.0)
            elif drag.axis is Axis.Y:
                delta = Vector2(0.0, delta.y)
            moved = start_position + delta
            # Snapped in absolute world space, not by snapping the delta:
            # snapping the delta leaves an entity that began off-grid off
            # it for ever, which is never what dragging onto a grid means.
            return state.snap_point(moved), start_rotation, start_scale

        if drag.mode is GizmoMode.ROTATE:
            offset = cursor_world - drag.pivot
            angle = math.atan2(offset.y, offset.x)
            rotation = start_rotation + (angle - drag.start_angle)
            if state.snap:
                step = math.radians(ROTATION_SNAP_DEGREES)
                rotation = round(rotation / step) * step
            return start_position, rotation, start_scale

        offset = cursor_world - drag.pivot
        factor = max(offset.length, 1e-3) / drag.start_distance
        if state.snap:
            factor = max(
                SCALE_SNAP_STEP,
                round(factor / SCALE_SNAP_STEP) * SCALE_SNAP_STEP,
            )
        scale_x = start_scale.x * (factor if drag.axis is not Axis.Y else 1.0)
        scale_y = start_scale.y * (factor if drag.axis is not Axis.X else 1.0)
        return start_position, start_rotation, Vector2(scale_x, scale_y)

    def _restore(self, drag: _DragState) -> None:
        """Put every entity back to its drag-start transform.

        Args:
            drag: The abandoned drag.
        """
        manager = self._session.world
        for entity_id, (position, rotation, scale) in drag.start_values.items():
            transform = self._transform_of(manager, entity_id)
            if transform is None:
                continue
            transform.position = position
            transform.rotation = rotation
            transform.scale = scale
            manager.notify_component_changed(entity_id, Transform)

    @staticmethod
    def _label(drag: _DragState, count: int) -> str:
        """Return the history label for a finished drag.

        Args:
            drag: The finished drag.
            count: How many entities it moved.

        Returns:
            The label.
        """
        verb = {
            GizmoMode.TRANSLATE: "Move",
            GizmoMode.ROTATE: "Rotate",
            GizmoMode.SCALE: "Scale",
        }[drag.mode]
        return f"{verb} {count} entit{'y' if count == 1 else 'ies'}"

    # ----------------------------------------------------------------
    # Handles
    # ----------------------------------------------------------------

    def _handles(self, centre: Vector2) -> list[_Handle]:
        """Return this frame's handles for the current mode.

        Args:
            centre: The pivot, in panel coordinates.

        Returns:
            The handles, in hit-test priority order -- the single-axis
            ones first, so an arrow tip wins over the free-move square it
            overlaps near the origin.
        """
        if self._mode is GizmoMode.TRANSLATE:
            return [
                _Handle(Axis.X, Vector2(centre.x + AXIS_LENGTH, centre.y)),
                _Handle(Axis.Y, Vector2(centre.x, centre.y - AXIS_LENGTH)),
                _Handle(Axis.BOTH, centre),
            ]
        if self._mode is GizmoMode.ROTATE:
            return [_Handle(Axis.BOTH, Vector2(centre.x + ROTATE_RADIUS, centre.y))]
        return [
            _Handle(Axis.X, Vector2(centre.x + AXIS_LENGTH, centre.y)),
            _Handle(Axis.Y, Vector2(centre.x, centre.y - AXIS_LENGTH)),
            _Handle(
                Axis.BOTH,
                Vector2(centre.x + AXIS_LENGTH * 0.7, centre.y - AXIS_LENGTH * 0.7),
            ),
        ]

    @staticmethod
    def _handle_under(handles: list[_Handle], cursor: Vector2) -> Axis | None:
        """Return the axis of the handle under `cursor`, or None.

        Args:
            handles: This frame's handles, in priority order.
            cursor: The cursor, in panel coordinates.

        Returns:
            The grabbed axis, or None.
        """
        for handle in handles:
            if (handle.position - cursor).length <= HANDLE_GRAB_RADIUS:
                return handle.axis
        return None

    def _draw_handles(
        self,
        draw_list: Any,
        state: ViewportState,
        centre: Vector2,
        handles: list[_Handle],
    ) -> None:
        """Draw the gizmo for the current mode.

        Args:
            draw_list: The panel's ImGui draw list.
            state: The viewport's geometry, for the panel origin.
            centre: The pivot, in panel coordinates.
            handles: This frame's handles.
        """
        if draw_list is None:  # pragma: no cover - headless overlay tests
            return

        offset = Vector2(state.content.x, state.content.y)
        active = self._drag.axis if self._drag is not None else None

        def point(position: Vector2) -> Any:
            return imgui.ImVec2(position.x + offset.x, position.y + offset.y)

        def colour_for(axis: Axis, default: int) -> int:
            if active is axis or (active is None and self._hovered is axis):
                return _HOVER_COLOUR
            return default

        if self._mode is GizmoMode.ROTATE:
            draw_list.add_circle(
                point(centre),
                ROTATE_RADIUS,
                colour_for(Axis.BOTH, _ROTATE_COLOUR),
                48,
                2.0,
            )
            draw_list.add_circle_filled(
                point(handles[0].position),
                4.0,
                colour_for(Axis.BOTH, _ROTATE_COLOUR),
            )
            return

        x_handle, y_handle = handles[0], handles[1]
        x_colour = colour_for(Axis.X, _X_COLOUR)
        y_colour = colour_for(Axis.Y, _Y_COLOUR)
        draw_list.add_line(point(centre), point(x_handle.position), x_colour, 2.0)
        draw_list.add_line(point(centre), point(y_handle.position), y_colour, 2.0)

        if self._mode is GizmoMode.TRANSLATE:
            self._arrow_head(draw_list, point, x_handle.position, 0.0, x_colour)
            self._arrow_head(
                draw_list, point, y_handle.position, -math.pi / 2, y_colour
            )
            free = colour_for(Axis.BOTH, _BOTH_COLOUR)
            draw_list.add_rect_filled(
                point(Vector2(centre.x - 4, centre.y - 4)),
                point(Vector2(centre.x + 4, centre.y + 4)),
                free,
            )
            return

        for handle, handle_colour in (
            (x_handle, x_colour),
            (y_handle, y_colour),
            (handles[2], colour_for(Axis.BOTH, _SCALE_COLOUR)),
        ):
            draw_list.add_rect_filled(
                point(
                    Vector2(
                        handle.position.x - SCALE_HANDLE,
                        handle.position.y - SCALE_HANDLE,
                    )
                ),
                point(
                    Vector2(
                        handle.position.x + SCALE_HANDLE,
                        handle.position.y + SCALE_HANDLE,
                    )
                ),
                handle_colour,
            )

    @staticmethod
    def _arrow_head(
        draw_list: Any,
        point: Any,
        tip: Vector2,
        angle: float,
        colour: int,
    ) -> None:
        """Draw a filled triangle at an arrow's tip.

        The geometry is `pyguara/tools/gizmos.py`'s, which was the part of
        it worth keeping.

        Args:
            draw_list: The panel's ImGui draw list.
            point: Converts a panel position to an ImGui one.
            tip: Where the arrow ends, in panel coordinates.
            angle: Which way it points, in radians.
            colour: The fill colour.
        """
        back = math.radians(150)
        left = Vector2(
            tip.x + ARROW_HEAD * math.cos(angle - back),
            tip.y + ARROW_HEAD * math.sin(angle - back),
        )
        right = Vector2(
            tip.x + ARROW_HEAD * math.cos(angle + back),
            tip.y + ARROW_HEAD * math.sin(angle + back),
        )
        draw_list.add_triangle_filled(point(tip), point(left), point(right), colour)

    # ----------------------------------------------------------------
    # Small helpers
    # ----------------------------------------------------------------

    def _pivot_id(self, context: PanelContext, manager: EntityManager) -> str | None:
        """Return the entity the gizmo anchors to.

        The primary selection -- the last one clicked -- when it has a
        `Transform`, and otherwise the first selected entity that does.
        The fallback matters because a selection routinely mixes things
        that can be moved with things that cannot: a UI entity, a
        singleton holding game state, an empty used as a tag. Giving up
        because the last click landed on one of those would make the
        gizmo vanish for no reason the user could see.

        Args:
            context: The selection to read.
            manager: The world.

        Returns:
            The pivot's id, or None when nothing selected can be moved.
        """
        primary = context.selection.entity_id
        if primary is not None and self._transform_of(manager, primary):
            return primary
        for entity_id in context.selection.entity_ids:
            if self._transform_of(manager, entity_id) is not None:
                return entity_id
        return None

    @staticmethod
    def _transform_of(manager: EntityManager, entity_id: str) -> Transform | None:
        """Return an entity's transform, or None.

        Args:
            manager: The world.
            entity_id: The entity.

        Returns:
            Its transform, or None when the entity or component is gone.
        """
        entity = manager.get_entity(entity_id)
        if entity is None or not entity.has_component(Transform):
            return None
        return entity.get_component(Transform)

    @staticmethod
    def _cursor_in_panel(state: ViewportState) -> Vector2:
        """Return the cursor relative to the panel's content origin.

        Args:
            state: The viewport's geometry.

        Returns:
            The cursor position.
        """
        mouse = imgui.get_io().mouse_pos
        return Vector2(mouse.x - state.content.x, mouse.y - state.content.y)

    @staticmethod
    def _to_panel(
        camera: Camera2D, state: ViewportState, world_point: Vector2
    ) -> Vector2:
        """Map a world position into panel coordinates.

        Args:
            camera: The camera the frame was rendered with.
            state: The viewport's geometry.
            world_point: The world position.

        Returns:
            The panel-relative position.
        """
        return world_to_panel(camera, world_point, state.content, state.target)

    @staticmethod
    def _to_world(
        camera: Camera2D, state: ViewportState, panel_point: Vector2
    ) -> Vector2:
        """Map a panel-relative point into world coordinates.

        Args:
            camera: The camera the frame was rendered with.
            state: The viewport's geometry.
            panel_point: The panel-relative position.

        Returns:
            The world position.
        """
        return screen_to_world(camera, panel_point, state.content, state.target)
