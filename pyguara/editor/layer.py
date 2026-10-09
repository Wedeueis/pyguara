"""The editor layer: ImGui context lifecycle, panels, and per-frame input.

Deliberately separable from GL. `EditorLayer` builds a frame -- feeds IO,
runs `new_frame()`, draws every visible panel, calls `render()` -- and only
then hands the resulting draw data to a renderer, which may be `None`. That
split is what makes the panels testable: `imgui.create_context()` needs no
OpenGL at all, so a test runs real frames against a real world and asserts
on what the panels did, with no window, no context sharing and no GPU.

The previous editor had no such seam -- every panel method early-returned
behind a dead GL import -- which is how 705 lines of it stayed untested and
unexecuted until it was deleted.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from imgui_bundle import imgui

from pyguara.di.container import DIContainer
from pyguara.ecs.manager import EntityManager
from pyguara.editor.availability import require_imgui
from pyguara.editor.input import feed_event, wants_keyboard, wants_mouse
from pyguara.editor.panels.base import EditorPanel, PanelContext
from pyguara.editor.panels.hierarchy import HierarchyPanel
from pyguara.editor.panels.inspector import InspectorPanel
from pyguara.editor.renderer import ModernGLImGuiRenderer
from pyguara.editor.selection import Selection
from pyguara.log import get_logger

logger = get_logger(__name__)

_DOCKSPACE_ID = 1
"""The host dockspace's ImGui id.

Any non-zero constant works; ImGui only needs it stable across frames so a
dock layout persists.
"""


@dataclass(frozen=True)
class DockLayout:
    """Where each panel opens, by window title.

    Titles rather than panel objects, because that is what ImGui's dock
    builder keys on -- and it means a layout can name a panel that has
    not been added yet, which is how a caller can describe an arrangement
    once instead of rebuilding it as panels arrive.

    Attributes:
        left: Titles docked to the left edge.
        right: Titles docked to the right edge.
        bottom: Titles docked along the bottom.
        centre: Titles filling what is left, which is the largest region.
        left_ratio: How much of the width the left edge takes.
        right_ratio: How much of the remaining width the right edge takes.
        bottom_ratio: How much of the remaining height the bottom takes.
    """

    left: tuple[str, ...] = ()
    right: tuple[str, ...] = ()
    bottom: tuple[str, ...] = ()
    centre: tuple[str, ...] = ()
    left_ratio: float = 0.20
    right_ratio: float = 0.25
    bottom_ratio: float = 0.28


def default_panels() -> list[EditorPanel]:
    """Return the panel set the editor ships with.

    Returns:
        A fresh Hierarchy and Inspector panel.
    """
    return [HierarchyPanel(), InspectorPanel()]


class EditorLayer:
    """Owns an ImGui context and draws the editor's panels over the game."""

    def __init__(
        self,
        container: DIContainer,
        *,
        renderer_factory: Callable[[], ModernGLImGuiRenderer] | None = None,
        panels: list[EditorPanel] | None = None,
    ) -> None:
        """Create the ImGui context and install the panels.

        Args:
            container: The engine container, used to find the active scene's
                world each frame.
            renderer_factory: Builds the renderer that rasterises the draw
                data, called *after* this layer's ImGui context exists and
                is current. It is a factory rather than a ready-made
                renderer because `ModernGLImGuiRenderer.__init__` declares
                its capabilities on `imgui.get_io()`, which would otherwise
                land on whichever context happened to be current when the
                caller built it. `None` builds frames without drawing them,
                which is how the headless tests run.
            panels: Panels to draw. Defaults to `default_panels()`.

        Raises:
            RuntimeError: If ImGui is not installed.
        """
        require_imgui()

        self._container = container
        self._panels: list[EditorPanel] = (
            default_panels() if panels is None else list(panels)
        )
        self._selection = Selection()
        self._visible = True
        self._last_frame_time: float | None = None

        self._layout: DockLayout | None = None
        self._layout_applied = False

        self._context = imgui.create_context()
        # A fresh context starts as the current one, but not necessarily the
        # only one -- tests create several, and whichever was made last would
        # otherwise receive this layer's calls.
        imgui.set_current_context(self._context)
        io = imgui.get_io()
        io.config_flags |= imgui.ConfigFlags_.nav_enable_keyboard.value
        # Docking. What makes this an editor layout rather than a pile of
        # floating windows: panels snap into splits and tabs, and a
        # developer's arrangement survives being nudged. `build_frame()`
        # submits the host dockspace each frame, before any panel, so every
        # panel is dockable without opting in.
        io.config_flags |= imgui.ConfigFlags_.docking_enable.value
        # Declared by the layer, not only by the renderer. ImGui 1.92
        # asserts in `new_frame()` unless the backend claims the dynamic
        # texture system -- it otherwise expects a legacy backend to have
        # uploaded the font atlas itself. A layer with no renderer still
        # builds frames (that is how the panels are tested), and nothing
        # consumes the atlas in that mode, so claiming it here is both
        # safe and necessary. `ModernGLImGuiRenderer` sets the same bit for
        # when it is driven on its own.
        io.backend_flags |= imgui.BackendFlags_.renderer_has_textures.value
        # Nothing here writes imgui.ini: a dev tool silently dropping a file
        # into the project root is a surprise, and panel layout is cheap to
        # re-arrange.
        io.set_ini_filename("")

        # Built last, and only now: the context above is current, so the
        # renderer's `backend_flags` reach this layer's IO and not another's.
        self._renderer: ModernGLImGuiRenderer | None = (
            renderer_factory() if renderer_factory is not None else None
        )

    @property
    def is_released(self) -> bool:
        """Whether `release()` has run and this layer is spent."""
        return self._context is None

    @property
    def panels(self) -> list[EditorPanel]:
        """The panels this layer draws, in draw order."""
        return list(self._panels)

    @property
    def selection(self) -> Selection:
        """The shared selection the panels read and write."""
        return self._selection

    @property
    def visible(self) -> bool:
        """Whether the editor draws at all."""
        return self._visible

    def toggle(self) -> None:
        """Show or hide the whole editor."""
        self._visible = not self._visible

    def add_panel(self, panel: EditorPanel) -> None:
        """Append a panel to the draw order.

        Args:
            panel: The panel to add.
        """
        self._panels.append(panel)

    def register_texture(self, texture: object) -> int | None:
        """Make a texture drawable by a panel, returning its ImGui id.

        Forwarded to the renderer, which owns the id space. A Studio
        viewport calls this with the render graph's framebuffer texture so
        it can show the rendered frame as an image.

        Returns None when this layer has no renderer, which is how the
        headless tests run -- a panel then has no texture to show and must
        say so rather than draw an image with a meaningless id.

        Args:
            texture: A `moderngl.Texture` on the renderer's context.

        Returns:
            The id to hand `imgui.image()`, or None.
        """
        if self._renderer is None:
            return None
        from typing import cast

        import moderngl

        return self._renderer.register_texture(cast(moderngl.Texture, texture))

    def process_event(self, event: object) -> bool:
        """Feed one engine event to ImGui and report whether it took it.

        Args:
            event: An engine event from `Window.poll_events()`.

        Returns:
            True when ImGui is using that kind of input this frame, so the
            caller should not also route the event to the game. Always
            False while the editor is hidden.
        """
        if not self._visible:
            return False

        imgui.set_current_context(self._context)
        feed_event(event)

        # `want_capture_*` reflects the frame just built, which is the best
        # answer available at event time: ImGui decides capture during
        # `new_frame()`, after the events for that frame have arrived.
        event_name = type(event).__name__
        if event_name.startswith("Mouse"):
            return wants_mouse()
        if event_name.startswith(("Key", "TextInput")):
            return wants_keyboard()
        return False

    def render(self, width: int, height: int, dt: float | None = None) -> None:
        """Build one editor frame and, if a renderer exists, draw it.

        Args:
            width: Target width in pixels.
            height: Target height in pixels.
            dt: Seconds since the previous frame. Measured here when None,
                which is what the render pass does -- `BaseRenderPass.execute`
                is handed no delta time.
        """
        if not self._visible or width <= 0 or height <= 0:
            return

        draw_data = self.build_frame(width, height, dt)
        if self._renderer is not None:
            self._renderer.render(draw_data)

    def build_frame(
        self, width: int, height: int, dt: float | None = None
    ) -> imgui.ImDrawData:
        """Run one ImGui frame over the live world and return its draw data.

        Args:
            width: Target width in pixels.
            height: Target height in pixels.
            dt: Seconds since the previous frame, measured here when None.

        Returns:
            The frame's draw data, ready for a renderer.
        """
        imgui.set_current_context(self._context)

        io = imgui.get_io()
        io.display_size = imgui.ImVec2(float(width), float(height))
        # ImGui requires a strictly positive delta; two frames inside one
        # clock tick would otherwise trip its assert.
        io.delta_time = max(self._measure_dt() if dt is None else dt, 1e-6)

        imgui.new_frame()
        # Before the menu bar and every panel: a panel docked into this
        # space is positioned by it, so the space has to exist first.
        self._submit_dockspace()
        context = PanelContext(
            entity_manager=self._active_entity_manager(),
            selection=self._selection,
        )
        self._draw_menu_bar()
        for panel in self._panels:
            if panel.visible:
                panel.draw(context)
        imgui.render()
        return imgui.get_draw_data()

    def _submit_dockspace(self) -> None:
        """Declare the full-viewport dockspace panels may dock into.

        `pass_thru_central_node` leaves the middle empty rather than
        painting it: the game is already on screen underneath, and a filled
        central node would hide it behind a flat panel background. Panels
        dragged to an edge split off around that hole.
        """
        imgui.dock_space_over_viewport(
            dockspace_id=_DOCKSPACE_ID,
            flags=imgui.DockNodeFlags_.passthru_central_node.value,
        )
        if self._layout is not None and not self._layout_applied:
            # After the dockspace exists -- the builder docks into it --
            # and before any panel's `begin`, which would otherwise take
            # its position for the frame and only snap into place on the
            # next one.
            self._layout_applied = True
            self._apply_layout(self._layout)

    def set_default_layout(self, layout: DockLayout | None) -> None:
        """Arrange the panels the next time a frame is built.

        Applied once rather than every frame, so a developer who drags a
        panel somewhere else keeps it there. Without a layout every window
        opens at the same default position, stacked on top of each other,
        which is what an editor with docking enabled and no arrangement
        looks like.

        Args:
            layout: Where each panel goes, or None to leave ImGui's
                defaults alone.
        """
        self._layout = layout
        self._layout_applied = False

    def _apply_layout(self, layout: DockLayout) -> None:
        """Build the dock tree and assign panels to its regions.

        Args:
            layout: Which panel titles belong in which region.
        """
        internal = imgui.internal
        root = _DOCKSPACE_ID

        internal.dock_builder_remove_node(root)
        internal.dock_builder_add_node(
            root, imgui.internal.DockNodeFlagsPrivate_.dock_space.value
        )
        internal.dock_builder_set_node_size(root, imgui.get_io().display_size)

        # Split off each side in turn. Every split returns the new node and
        # what is left of the one it came from, and the remainder becomes
        # the thing to split next -- so the centre shrinks as sides are
        # taken, and ends up as the viewport's home.
        centre = root
        regions: dict[str, int] = {}
        for name, direction, ratio in (
            ("left", imgui.Dir.left, layout.left_ratio),
            ("right", imgui.Dir.right, layout.right_ratio),
            ("bottom", imgui.Dir.down, layout.bottom_ratio),
        ):
            split = internal.dock_builder_split_node(centre, direction, ratio)
            regions[name] = split.id_at_dir
            centre = split.id_at_opposite_dir
        regions["centre"] = centre

        for region, titles in (
            ("left", layout.left),
            ("right", layout.right),
            ("bottom", layout.bottom),
            ("centre", layout.centre),
        ):
            for title in titles:
                internal.dock_builder_dock_window(title, regions[region])

        internal.dock_builder_finish(root)
        logger.debug("Applied the default dock layout.")

    def _draw_menu_bar(self) -> None:
        """Draw the panel-visibility menu across the top of the window."""
        if not imgui.begin_main_menu_bar():
            return
        try:
            if imgui.begin_menu("Panels", True):
                try:
                    for panel in self._panels:
                        clicked, _ = imgui.menu_item(panel.title, "", panel.visible)
                        if clicked:
                            panel.toggle()
                finally:
                    imgui.end_menu()
        finally:
            imgui.end_main_menu_bar()

    def _measure_dt(self) -> float:
        """Return seconds since the previous measured frame.

        Returns:
            The elapsed time, or a single 60Hz step on the first frame.
        """
        now = time.perf_counter()
        if self._last_frame_time is None:
            self._last_frame_time = now
            return 1.0 / 60.0
        elapsed = now - self._last_frame_time
        self._last_frame_time = now
        return elapsed

    def _active_entity_manager(self) -> EntityManager | None:
        """Return the active scene's world, or None if no scene is active.

        Resolved every frame rather than cached: each scene owns its own
        `EntityManager` (there is no global one in the container), so the
        answer changes on every scene switch.

        Unlike `pyguara/tools/base.py`, which substitutes a throwaway empty
        manager during the no-scene window, this returns None and lets the
        panels say "no active scene" -- an empty world and no world at all
        look identical otherwise.

        Returns:
            The current scene's entity manager, or None.
        """
        from pyguara.scene.manager import SceneManager

        try:
            scene_manager = self._container.get(SceneManager)
        except Exception:  # pragma: no cover - a container without a scene manager
            return None

        current_scene = scene_manager.current_scene
        if current_scene is None:
            return None
        return current_scene.entity_manager

    def release(self) -> None:
        """Destroy the ImGui context and release the renderer's resources.

        Safe to call more than once.
        """
        if self._renderer is not None:
            self._renderer.release()
            self._renderer = None
        if self._context is not None:
            imgui.destroy_context(self._context)
            self._context = None  # type: ignore[assignment]
