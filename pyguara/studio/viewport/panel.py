"""The scene viewport: the rendered frame, with editing on top of it.

An ImGui panel showing the render graph's own framebuffer as an image,
with pan, zoom, a grid, selection and a marquee drawn over it. The frame
is the one the engine already rendered -- there is no second render path
to keep in step, and what the viewport shows is by construction what the
game shows.

Two things make that work, and both were added for this:

- `ModernGLImGuiRenderer.register_texture()`, because `_textures` was
  populated only from ImGui's own atlas requests and `imgui.image()` with
  any other id drew nothing, silently.
- A docked ImGui layout, so the panel has somewhere to live.

**The panel is not the framebuffer.** It shows a frame rendered at the
game's resolution, scaled into whatever size a docked panel happens to
be, so every coordinate crosses two mappings: panel space to framebuffer
space, then framebuffer space to world through the camera.
`picking.screen_to_world` and `picking.world_to_panel` are that pair, and
they have to agree exactly -- a gizmo handle drawn where it cannot be
grabbed is the classic symptom of them not.

Pan and zoom drive the scene's own `Camera2D`, which is what the render
path already reads. An editor camera that the renderer did not consult
would show a frame that moved while nothing else agreed it had.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from imgui_bundle import imgui

from pyguara.common.types import Rect, Vector2
from pyguara.editor.panels.base import EditorPanel, PanelContext
from pyguara.graphics.components.camera import Camera2D
from pyguara.log import get_logger
from pyguara.studio.viewport.picking import (
    Pick,
    iter_pickable,
    marquee_rect,
    pick_at,
    pick_in_region,
    screen_to_world,
    world_to_panel,
)

logger = get_logger(__name__)

MIN_ZOOM = 0.05
"""Furthest out the viewport will go.

`Camera2D.zoom` rejects anything at or below zero, and a value this small
already shows a 20x area; going further is all cost and no use.
"""

MAX_ZOOM = 20.0
"""Closest in. Past this a single world unit is larger than the panel."""

ZOOM_STEP = 1.15
"""Multiplier per wheel notch. Geometric, so zooming feels the same at
every scale -- an additive step crawls when zoomed out and lurches when
zoomed in."""

GRID_MIN_SPACING = 8.0
"""Below this many pixels apart, a grid line is noise and is skipped."""

_GRID_COLOUR = imgui.IM_COL32(255, 255, 255, 28)
_GRID_AXIS_COLOUR = imgui.IM_COL32(255, 255, 255, 70)
_SELECTION_COLOUR = imgui.IM_COL32(255, 210, 60, 255)
_PRIMARY_COLOUR = imgui.IM_COL32(255, 255, 255, 255)
_MARQUEE_FILL = imgui.IM_COL32(90, 160, 255, 40)
_MARQUEE_EDGE = imgui.IM_COL32(120, 190, 255, 200)


@dataclass
class ViewportState:
    """What the viewport remembers between frames.

    Attributes:
        grid_size: World units between grid lines. Also the snap step.
        show_grid: Whether to draw the grid.
        snap: Whether a drag snaps to the grid.
        enclose_select: Whether a marquee selects only fully enclosed
            entities, rather than anything it touches.
        panning: Whether a pan drag is in progress.
        marquee_start: Where a marquee drag began, in world space, or None.
        content: The panel's content area in window coordinates, as of the
            last frame. Read by the gizmo, which draws into the same space.
        target: The framebuffer's size as rendered, from the last frame.
    """

    grid_size: float = 32.0
    show_grid: bool = True
    snap: bool = False
    enclose_select: bool = False
    panning: bool = False
    marquee_start: Vector2 | None = None
    content: Rect = field(default_factory=lambda: Rect(0, 0, 0, 0))
    target: Rect = field(default_factory=lambda: Rect(0, 0, 0, 0))

    @property
    def has_geometry(self) -> bool:
        """Whether the last frame gave usable panel and target sizes.

        False before the first frame, and whenever the panel is collapsed
        to nothing -- both cases where a coordinate mapping would divide
        by zero.
        """
        return (
            self.content.width > 0
            and self.content.height > 0
            and self.target.width > 0
            and self.target.height > 0
        )

    def snap_value(self, value: float) -> float:
        """Round `value` to the grid when snapping is on.

        Args:
            value: A world-space coordinate.

        Returns:
            The snapped value, or `value` unchanged.
        """
        if not self.snap or self.grid_size <= 0:
            return value
        return round(value / self.grid_size) * self.grid_size

    def snap_point(self, point: Vector2) -> Vector2:
        """Round a world position to the grid when snapping is on.

        Args:
            point: The world position.

        Returns:
            The snapped position.
        """
        if not self.snap:
            return point
        return Vector2(self.snap_value(point.x), self.snap_value(point.y))


class ViewportOverlay:
    """Something that draws into the viewport and may consume its input.

    The seam the transform gizmo plugs into. The viewport owns the panel,
    the camera and the coordinate mappings; an overlay is handed those and
    says whether it used the mouse this frame -- which is what stops a
    gizmo drag from also starting a marquee.
    """

    def draw(
        self,
        context: PanelContext,
        state: ViewportState,
        camera: Camera2D,
        draw_list: Any,
    ) -> bool:
        """Draw, and report whether the mouse was consumed.

        Args:
            context: The world and selection.
            state: The viewport's geometry and snap settings.
            camera: The camera the frame was rendered with.
            draw_list: The ImGui draw list for the panel.

        Returns:
            True when this overlay is using the mouse, so the viewport
            must not also pick or marquee with it.
        """
        return False


class ViewportPanel(EditorPanel):
    """Shows the rendered scene, and lets it be selected in and navigated."""

    def __init__(
        self,
        *,
        camera_provider: Any = None,
        texture_provider: Any = None,
        physics_provider: Any = None,
        overlays: list[ViewportOverlay] | None = None,
        visible: bool = True,
    ) -> None:
        """Initialize the panel.

        Everything the viewport needs from outside arrives as a callable
        rather than an object, because all three answers change: the
        camera belongs to whichever scene is active, the texture to
        whichever framebuffer the graph last resized, and the physics
        engine may not exist. A captured reference would be stale after
        the first scene switch.

        Args:
            camera_provider: Returns the active `Camera2D`, or None.
            texture_provider: Returns `(texture_id, width, height)` for the
                frame to show, or None when there is nothing to show.
            physics_provider: Returns an `IPhysicsEngine`, or None.
            overlays: Things that draw over the image, such as the gizmo.
            visible: Whether the panel draws from the first frame.
        """
        super().__init__("Viewport", visible=visible)
        self._camera_provider = camera_provider
        self._texture_provider = texture_provider
        self._physics_provider = physics_provider
        self._overlays = list(overlays or [])
        self._state = ViewportState()

    @property
    def state(self) -> ViewportState:
        """The viewport's geometry and settings."""
        return self._state

    def add_overlay(self, overlay: ViewportOverlay) -> None:
        """Add something that draws over the image.

        Args:
            overlay: The overlay to add.
        """
        self._overlays.append(overlay)

    def draw(self, context: PanelContext) -> None:
        """Draw one frame of the viewport.

        Args:
            context: The world and selection to read.
        """
        imgui.begin(self.title)
        try:
            self._draw_toolbar()
            manager = context.entity_manager
            if manager is None:
                imgui.text_disabled("No active scene.")
                return

            camera = self._resolve(self._camera_provider)
            if camera is None:
                imgui.text_disabled("No camera. The scene has one once it is entered.")
                return

            self._draw_viewport(context, camera)
        finally:
            # Dear ImGui owes an End for every Begin, collapsed or not.
            imgui.end()

    def _draw_toolbar(self) -> None:
        """Draw the grid, snap and selection-mode controls."""
        _, self._state.show_grid = imgui.checkbox("Grid", self._state.show_grid)
        imgui.same_line()
        _, self._state.snap = imgui.checkbox("Snap", self._state.snap)
        imgui.same_line()
        imgui.set_next_item_width(90)
        changed, grid_size = imgui.drag_float(
            "Step", self._state.grid_size, 1.0, 1.0, 512.0
        )
        if changed:
            self._state.grid_size = max(1.0, grid_size)
        imgui.same_line()
        _, self._state.enclose_select = imgui.checkbox(
            "Enclose", self._state.enclose_select
        )

    def _draw_viewport(self, context: PanelContext, camera: Camera2D) -> None:
        """Draw the image, the overlays and the interaction.

        Args:
            context: The world and selection.
            camera: The active camera.
        """
        content_size = imgui.get_content_region_avail()
        if content_size.x < 1 or content_size.y < 1:
            return

        origin = imgui.get_cursor_screen_pos()
        self._state.content = Rect(
            int(origin.x), int(origin.y), int(content_size.x), int(content_size.y)
        )

        frame = self._resolve(self._texture_provider)
        if frame is None:
            # The common case on the Pygame backend, which has no GL
            # context and so no texture to hand over. Saying so beats an
            # empty panel that looks like a broken render path.
            imgui.text_disabled(
                "No rendered frame available. The viewport needs the ModernGL backend."
            )
            return

        texture_id, target_width, target_height = frame
        self._state.target = Rect(0, 0, int(target_width), int(target_height))

        # The framebuffer's origin is bottom-left and ImGui's is top-left,
        # so the V coordinate is flipped here rather than the image being
        # mirrored anywhere else. Getting this wrong renders a frame that
        # looks plausible and picks upside down.
        # `ImTextureRef`, not the bare int: ImGui 1.92 wraps a texture id
        # in one, and passing the int raises rather than drawing. The ref
        # carries the same id straight back out through `get_tex_id()`,
        # which is what `ModernGLImGuiRenderer`'s draw loop resolves
        # against the ids `register_texture()` minted.
        imgui.image(
            imgui.ImTextureRef(texture_id),
            imgui.ImVec2(content_size.x, content_size.y),
            imgui.ImVec2(0.0, 1.0),
            imgui.ImVec2(1.0, 0.0),
        )
        hovered = imgui.is_item_hovered()

        draw_list = imgui.get_window_draw_list()
        if self._state.show_grid:
            self._draw_grid(camera, draw_list)

        consumed = False
        for overlay in self._overlays:
            if overlay.draw(context, self._state, camera, draw_list):
                consumed = True

        self._draw_selection(context, camera, draw_list)

        if not consumed:
            self._handle_input(context, camera, hovered=hovered)
        self._draw_marquee(camera, draw_list)

    # ----------------------------------------------------------------
    # Input
    # ----------------------------------------------------------------

    def _handle_input(
        self, context: PanelContext, camera: Camera2D, *, hovered: bool
    ) -> None:
        """Pan, zoom, pick and marquee.

        Args:
            context: The world and selection.
            camera: The camera to move.
            hovered: Whether the cursor is over the image.
        """
        io = imgui.get_io()

        # A pan or marquee already in progress keeps going even once the
        # cursor leaves the panel; a drag that cancelled itself at the
        # edge would be unusable.
        if self._state.panning:
            self._continue_pan(camera, io)
        elif self._state.marquee_start is not None:
            self._continue_marquee(context, camera, io)

        if not hovered:
            return

        if io.mouse_wheel != 0.0:
            self._zoom(camera, io.mouse_wheel)

        # Middle-drag, or space-drag, to pan. Both conventions exist and
        # neither costs anything to support.
        if not self._state.panning and (
            imgui.is_mouse_dragging(imgui.MouseButton_.middle)
            or (
                imgui.is_key_down(imgui.Key.space)
                and imgui.is_mouse_dragging(imgui.MouseButton_.left)
            )
        ):
            self._state.panning = True
            return

        if imgui.is_mouse_clicked(imgui.MouseButton_.left) and not imgui.is_key_down(
            imgui.Key.space
        ):
            self._pick(context, camera, io, additive=io.key_ctrl or io.key_shift)

        if (
            self._state.marquee_start is None
            and imgui.is_mouse_dragging(imgui.MouseButton_.left)
            and not imgui.is_key_down(imgui.Key.space)
        ):
            self._state.marquee_start = self._world_at_cursor(camera, io)

    def _continue_pan(self, camera: Camera2D, io: Any) -> None:
        """Move the camera by this frame's mouse delta.

        Divided by zoom, so a pan drags the picture under the cursor by
        the same number of *pixels* at every zoom level -- the thing the
        hand is doing.

        Args:
            camera: The camera to move.
            io: ImGui's IO, for the mouse delta.
        """
        still_dragging = imgui.is_mouse_down(imgui.MouseButton_.middle) or (
            imgui.is_key_down(imgui.Key.space)
            and imgui.is_mouse_down(imgui.MouseButton_.left)
        )
        if not still_dragging:
            self._state.panning = False
            return

        delta = io.mouse_delta
        if delta.x == 0.0 and delta.y == 0.0:
            return
        scale = self._panel_to_target_scale()
        camera.position = camera.position - Vector2(
            (delta.x * scale.x) / camera.zoom, (delta.y * scale.y) / camera.zoom
        )

    def _zoom(self, camera: Camera2D, wheel: float) -> None:
        """Zoom about the cursor, so the point under it stays put.

        The behaviour everyone expects and nobody describes: anchor the
        world position under the cursor, change the zoom, then move the
        camera so that world position lands under the cursor again.
        Zooming about the screen centre instead sends whatever you were
        looking at off the edge.

        Args:
            camera: The camera to zoom.
            wheel: Wheel notches, positive for in.
        """
        if not self._state.has_geometry:
            return

        io = imgui.get_io()
        anchor = self._world_at_cursor(camera, io)
        target = camera.zoom * (ZOOM_STEP**wheel)
        clamped = max(MIN_ZOOM, min(MAX_ZOOM, target))
        if clamped == camera.zoom:
            return

        camera.zoom = clamped
        after = self._world_at_cursor(camera, io)
        camera.position = camera.position + (anchor - after)

    def _pick(
        self, context: PanelContext, camera: Camera2D, io: Any, *, additive: bool
    ) -> None:
        """Select whatever is under the cursor.

        Args:
            context: The world and selection.
            camera: The camera the frame was rendered with.
            io: ImGui's IO, for the cursor position.
            additive: Add to the selection rather than replacing it.
        """
        manager = context.entity_manager
        if manager is None or not self._state.has_geometry:
            return

        hit = pick_at(
            manager,
            self._world_at_cursor(camera, io),
            physics=self._resolve(self._physics_provider),
        )
        if hit is None:
            # Clicking empty space clears, unless adding -- a ctrl-click
            # that missed should not throw away a careful selection.
            if not additive:
                context.selection.clear()
            return

        if additive:
            context.selection.toggle(hit.entity_id)
        else:
            context.selection.select(hit.entity_id)

    def _continue_marquee(
        self, context: PanelContext, camera: Camera2D, io: Any
    ) -> None:
        """Update, or finish, a marquee drag.

        Args:
            context: The world and selection.
            camera: The camera the frame was rendered with.
            io: ImGui's IO, for the cursor position.
        """
        if imgui.is_mouse_down(imgui.MouseButton_.left):
            return

        start = self._state.marquee_start
        self._state.marquee_start = None
        manager = context.entity_manager
        if start is None or manager is None:
            return

        region = marquee_rect(start, self._world_at_cursor(camera, io))
        picks: list[Pick] = pick_in_region(
            manager,
            region,
            require_full_containment=self._state.enclose_select,
        )
        if io.key_ctrl or io.key_shift:
            for pick in picks:
                context.selection.add(pick.entity_id)
        else:
            context.selection.select_many(pick.entity_id for pick in picks)

    # ----------------------------------------------------------------
    # Drawing
    # ----------------------------------------------------------------

    def _draw_grid(self, camera: Camera2D, draw_list: Any) -> None:
        """Draw the world grid, skipping it when the lines would merge.

        Args:
            camera: The camera the frame was rendered with.
            draw_list: The panel's ImGui draw list.
        """
        if not self._state.has_geometry or self._state.grid_size <= 0:
            return

        content = self._state.content
        spacing_px = (
            self._state.grid_size
            * camera.zoom
            / max(self._panel_to_target_scale().x, 1e-6)
        )
        if spacing_px < GRID_MIN_SPACING:
            return

        top_left = self._world_at_panel(camera, Vector2(0, 0))
        bottom_right = self._world_at_panel(
            camera, Vector2(content.width, content.height)
        )
        step = self._state.grid_size

        start_x = int(top_left.x // step) * step
        x = start_x
        while x <= bottom_right.x:
            panel_x = self._panel_at_world(camera, Vector2(x, 0)).x + content.x
            colour = _GRID_AXIS_COLOUR if abs(x) < 1e-6 else _GRID_COLOUR
            draw_list.add_line(
                imgui.ImVec2(panel_x, float(content.y)),
                imgui.ImVec2(panel_x, float(content.y + content.height)),
                colour,
            )
            x += step

        start_y = int(top_left.y // step) * step
        y = start_y
        while y <= bottom_right.y:
            panel_y = self._panel_at_world(camera, Vector2(0, y)).y + content.y
            colour = _GRID_AXIS_COLOUR if abs(y) < 1e-6 else _GRID_COLOUR
            draw_list.add_line(
                imgui.ImVec2(float(content.x), panel_y),
                imgui.ImVec2(float(content.x + content.width), panel_y),
                colour,
            )
            y += step

    def _draw_selection(
        self, context: PanelContext, camera: Camera2D, draw_list: Any
    ) -> None:
        """Outline every selected entity, the primary one brighter.

        Args:
            context: The world and selection.
            camera: The camera the frame was rendered with.
            draw_list: The panel's ImGui draw list.
        """
        manager = context.entity_manager
        if manager is None or not self._state.has_geometry:
            return
        if not len(context.selection):
            return

        selected = set(context.selection.entity_ids)
        content = self._state.content
        for pick in iter_pickable(manager):
            if pick.entity_id not in selected:
                continue
            top_left = self._panel_at_world(
                camera, Vector2(pick.bounds.x, pick.bounds.y)
            )
            bottom_right = self._panel_at_world(
                camera,
                Vector2(
                    pick.bounds.x + pick.bounds.width,
                    pick.bounds.y + pick.bounds.height,
                ),
            )
            colour = (
                _PRIMARY_COLOUR
                if context.selection.is_primary(pick.entity_id)
                else _SELECTION_COLOUR
            )
            draw_list.add_rect(
                imgui.ImVec2(top_left.x + content.x, top_left.y + content.y),
                imgui.ImVec2(bottom_right.x + content.x, bottom_right.y + content.y),
                colour,
                # (rounding, thickness). The binding orders these
                # differently from the C++ API, which puts flags second.
                0.0,
                2.0,
            )

    def _draw_marquee(self, camera: Camera2D, draw_list: Any) -> None:
        """Draw the marquee while a drag is in progress.

        Args:
            camera: The camera the frame was rendered with.
            draw_list: The panel's ImGui draw list.
        """
        start = self._state.marquee_start
        if start is None or not self._state.has_geometry:
            return

        content = self._state.content
        io = imgui.get_io()
        begin = self._panel_at_world(camera, start)
        end = self._panel_at_world(camera, self._world_at_cursor(camera, io))
        first = imgui.ImVec2(begin.x + content.x, begin.y + content.y)
        second = imgui.ImVec2(end.x + content.x, end.y + content.y)
        draw_list.add_rect_filled(first, second, _MARQUEE_FILL)
        draw_list.add_rect(first, second, _MARQUEE_EDGE)

    # ----------------------------------------------------------------
    # Coordinates
    # ----------------------------------------------------------------

    def _panel_to_target_scale(self) -> Vector2:
        """Return framebuffer pixels per panel pixel on each axis.

        Returns:
            The scale, or `(1, 1)` before the first frame.
        """
        content = self._state.content
        target = self._state.target
        if content.width <= 0 or content.height <= 0:
            return Vector2(1.0, 1.0)
        return Vector2(target.width / content.width, target.height / content.height)

    def _world_at_cursor(self, camera: Camera2D, io: Any) -> Vector2:
        """Return the world position under the cursor.

        Args:
            camera: The camera the frame was rendered with.
            io: ImGui's IO, for the cursor position.

        Returns:
            The world position.
        """
        content = self._state.content
        return self._world_at_panel(
            camera,
            Vector2(io.mouse_pos.x - content.x, io.mouse_pos.y - content.y),
        )

    def _world_at_panel(self, camera: Camera2D, panel_point: Vector2) -> Vector2:
        """Map a panel-relative point to world space.

        Args:
            camera: The camera the frame was rendered with.
            panel_point: The point, relative to the panel's content origin.

        Returns:
            The world position.
        """
        return screen_to_world(
            camera, panel_point, self._state.content, self._state.target
        )

    def _panel_at_world(self, camera: Camera2D, world_point: Vector2) -> Vector2:
        """Map a world position to a panel-relative point.

        Args:
            camera: The camera the frame was rendered with.
            world_point: The world position.

        Returns:
            The point, relative to the panel's content origin.
        """
        return world_to_panel(
            camera, world_point, self._state.content, self._state.target
        )

    @staticmethod
    def _resolve(provider: Any) -> Any:
        """Call a provider, returning None if it has none or it fails.

        A viewport that raised because the scene had not finished loading
        would take the whole editor frame down with it.

        Args:
            provider: A zero-argument callable, or None.

        Returns:
            Whatever it returned, or None.
        """
        if provider is None:
            return None
        try:
            return provider()
        except Exception as exc:
            logger.debug(f"Viewport provider failed: {exc}")
            return None


__all__ = [
    "GRID_MIN_SPACING",
    "MAX_ZOOM",
    "MIN_ZOOM",
    "ZOOM_STEP",
    "ViewportOverlay",
    "ViewportPanel",
    "ViewportState",
]
