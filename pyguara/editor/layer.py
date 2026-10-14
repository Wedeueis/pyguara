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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

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
from pyguara.editor.theme import apply_theme, scale_for
from pyguara.editor.titlebar import TitleBar
from pyguara.editor.toasts import ToastStack
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
        top: Titles docked along the top, above everything else -- where
            a transport bar belongs.
        centre: Titles filling what is left, which is the largest region.
        left_ratio: How much of the width the left edge takes.
        right_ratio: How much of the remaining width the right edge takes.
        bottom_ratio: How much of the remaining height the bottom takes.
        top_ratio: How much of the remaining height the top takes, or
            None to size it to exactly one row of controls. A fixed
            fraction cannot do that: the row's height depends on the UI
            scale, and a strip that fits at 1.0 clips the row at 1.25.
    """

    left: tuple[str, ...] = ()
    right: tuple[str, ...] = ()
    bottom: tuple[str, ...] = ()
    top: tuple[str, ...] = ()
    centre: tuple[str, ...] = ()
    left_ratio: float = 0.20
    right_ratio: float = 0.25
    bottom_ratio: float = 0.28
    top_ratio: float | None = None


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
        # Set when a caller asks for the shipped arrangement *now* --
        # View > Reset Layout -- which is the one case that overwrites
        # both a saved arrangement and whatever the developer dragged.
        self._force_layout = False
        self._settings_file: Path | None = None
        self._settings_restored = False
        # Leave the middle of the dockspace empty by default, so the game
        # shows through it. Studio turns this off: it draws the frame into
        # a Viewport panel, and a second copy of the game behind the
        # panels is what made the editor look unfinished.
        self._passthrough_centre = True
        self._frame_hooks: list[Callable[[], None]] = []

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
        # Nothing is written unless a caller asks, through
        # `set_settings_file`: a dev tool silently dropping an `imgui.ini`
        # into the project root is a surprise, and the bare editor and
        # every test want nothing on disk at all. Studio asks, because an
        # authoring tool that forgets your layout every time you close it
        # is an authoring tool you re-arrange every morning.
        io.set_ini_filename("")

        # A deliberate palette rather than ImGui's default, which is a
        # debug-overlay style -- square corners, thin separators, a blue
        # chosen to be visible rather than to be looked at for hours.
        apply_theme()
        # 0.0 is "not yet applied", so the first frame always sets it --
        # no real scale is ever zero.
        self._ui_scale = 0.0
        # Set when the window is borderless and the backend can move it.
        # None leaves the operating system's own title bar in place.
        self._title_bar: TitleBar | None = None
        self._toasts = ToastStack()
        # One source for the menus, drawn either into ImGui's main menu
        # bar or into the editor's own title bar. Studio replaces this
        # with its own set; on its own the editor offers the panel list.
        self._menus: list[tuple[str, Callable[[], None]]] = [
            ("Panels", self.draw_panel_menu_items)
        ]

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

    def add_frame_hook(self, hook: Callable[[], None]) -> None:
        """Call `hook` at the start of every frame, before any panel draws.

        The seam something needs when it must react to the world changing
        but owns no panel of its own. PyGuara Studio uses it to notice a
        scene becoming active: its session is per-scene and resolved
        lazily, and without a per-frame nudge nothing ever asks for one --
        so its panels were never installed under `app.run()`, which is the
        only way a game actually starts.

        A hook that raises is logged and dropped rather than taking the
        frame down with it; an editor that stops drawing is a worse
        failure than one component of it going quiet.

        Args:
            hook: Called once per frame, with no arguments.
        """
        self._frame_hooks.append(hook)

    def replace_panel(self, index: int, panel: EditorPanel) -> None:
        """Put `panel` where the one at `index` was.

        The draw order is the dock layout's order, so a replacement has to
        land in the same slot rather than at the end -- a panel appended
        instead would open loose while the layout kept a place for the one
        it replaced.

        Args:
            index: Where in the draw order to put it.
            panel: The replacement.

        Raises:
            IndexError: If `index` names no panel.
        """
        self._panels[index] = panel
        panel.toasts = self._toasts

    def add_panel(self, panel: EditorPanel) -> None:
        """Append a panel to the draw order.

        Args:
            panel: The panel to add.
        """
        self._panels.append(panel)
        # So the panel can say something on screen rather than only to the
        # log. A refused edit that reports nothing reads as a control that
        # does not work.
        panel.toasts = self._toasts

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
        self._apply_ui_scale(width, height)
        # ImGui requires a strictly positive delta; two frames inside one
        # clock tick would otherwise trip its assert.
        io.delta_time = max(self._measure_dt() if dt is None else dt, 1e-6)

        # Before `new_frame`, so a hook that adds a panel has it drawn on
        # this frame rather than the next.
        self._run_frame_hooks()

        imgui.new_frame()
        # Before the dockspace, which is inset below whatever it takes.
        self._draw_title_bar(width)
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
        # Last, so they sit over every panel. They take no input, so
        # nothing underneath becomes unclickable while one is up.
        self._toasts.draw(float(width), float(height))
        imgui.render()
        return imgui.get_draw_data()

    def _submit_inset_dockspace(self, flags: int, offset: float) -> None:
        """Submit a dockspace that starts below the editor's title bar.

        `dock_space_over_viewport` covers the whole viewport, so with a
        title bar of our own it would sit *under* the bar and swallow its
        clicks. The host window is submitted by hand instead, inset by the
        bar's height.

        Args:
            flags: Dock node flags.
            offset: How far down the dockspace starts, in pixels.
        """
        size = imgui.get_io().display_size
        imgui.set_next_window_pos(imgui.ImVec2(0.0, offset))
        imgui.set_next_window_size(imgui.ImVec2(size.x, max(size.y - offset, 1.0)))
        imgui.push_style_var(imgui.StyleVar_.window_rounding, 0.0)
        imgui.push_style_var(imgui.StyleVar_.window_border_size, 0.0)
        imgui.push_style_var(imgui.StyleVar_.window_padding, imgui.ImVec2(0.0, 0.0))
        imgui.begin(
            "##dockhost",
            None,
            imgui.WindowFlags_.no_decoration.value
            | imgui.WindowFlags_.no_move.value
            | imgui.WindowFlags_.no_saved_settings.value
            | imgui.WindowFlags_.no_bring_to_front_on_focus.value
            | imgui.WindowFlags_.no_docking.value
            | imgui.WindowFlags_.no_nav_focus.value,
        )
        imgui.pop_style_var(3)
        try:
            imgui.dock_space(_DOCKSPACE_ID, imgui.ImVec2(0.0, 0.0), flags)
        finally:
            imgui.end()

    def _draw_title_bar(self, width: int) -> None:
        """Draw the editor's own title bar, if it has one.

        Args:
            width: The window width in pixels.
        """
        if self._title_bar is not None:
            self._title_bar.draw(float(width))

    def _run_frame_hooks(self) -> None:
        """Run every frame hook, dropping any that raises.

        Iterates a copy, because a hook may legitimately add a panel or
        another hook -- which is most of why they exist.
        """
        for hook in list(self._frame_hooks):
            try:
                hook()
            except Exception as exc:
                logger.warning(f"Editor frame hook failed and was removed: {exc}")
                self._frame_hooks.remove(hook)

    def _apply_ui_scale(self, width: int, height: int) -> None:
        """Keep the chrome legible at this window size.

        ImGui's built-in font is a 13px bitmap meant for a debug overlay,
        and every size in the style is in pixels -- so an editor that is
        comfortable at 1280 wide is a squint at 4K. The scale is derived
        from the window and applied to the font and to every spacing,
        padding and rounding at once.

        Re-derived per frame but applied only on a change, because
        `scale_all_sizes` multiplies the style it is called on: applying
        it twice compounds. The style is rebuilt from a pristine copy each
        time rather than scaled again from where it already is.

        Args:
            width: The window width in pixels.
            height: The window height in pixels.
        """
        scale = scale_for(width, height)
        if scale == self._ui_scale:
            return
        self._ui_scale = scale

        style = imgui.get_style()
        apply_theme(style)
        if scale != 1.0:
            style.scale_all_sizes(scale)
        # `font_scale_main`, not the removed `io.font_global_scale`: ImGui
        # 1.92's dynamic font system rebuilds the atlas at the new size
        # rather than stretching a 13px bitmap, so scaled text is sharp
        # instead of blurry.
        style.font_scale_main = scale
        logger.debug(f"Editor UI scale is now {scale} for {width}x{height}.")

    @property
    def title_bar(self) -> TitleBar | None:
        """The editor's own title bar, or None when the OS draws one."""
        return self._title_bar

    def set_title_bar(self, title_bar: TitleBar | None) -> None:
        """Draw `title_bar` across the top of every frame.

        The bar is also given the panel menu, so that the menu lives in
        the one strip of chrome rather than in a second row below it, and
        the dock layout is rebuilt, since the space below the bar is a
        different height from the whole viewport.

        Args:
            title_bar: The bar, or None to leave the OS's own.
        """
        self._title_bar = title_bar
        if title_bar is not None and not title_bar.menus:
            title_bar.menus = self._menus
        self._layout_applied = False

    @property
    def ui_scale(self) -> float:
        """The scale the chrome is currently drawn at."""
        return self._ui_scale

    def _submit_dockspace(self) -> None:
        """Declare the full-viewport dockspace panels may dock into.

        `pass_thru_central_node` leaves the middle empty rather than
        painting it: the game is already on screen underneath, and a filled
        central node would hide it behind a flat panel background. Panels
        dragged to an edge split off around that hole.
        """
        flags = 0
        if self._passthrough_centre:
            flags |= imgui.DockNodeFlags_.passthru_central_node.value

        # Read before submitting: `dock_space` creates the root node, so
        # afterwards one always exists. A node here means the tree came
        # back from the settings file.
        restored = imgui.internal.dock_builder_get_node(_DOCKSPACE_ID) is not None

        offset = self._title_bar.height() if self._title_bar is not None else 0.0
        if offset > 0.0:
            self._submit_inset_dockspace(flags, offset)
        else:
            imgui.dock_space_over_viewport(dockspace_id=_DOCKSPACE_ID, flags=flags)
        if self._layout is None:
            return
        if self._layout_applied and not self._force_layout:
            return
        # A tree restored from the settings file wins: the builder would
        # overwrite what ImGui had just loaded, and with it every splitter
        # the developer dragged in the last session.
        if restored and not self._force_layout:
            self._layout_applied = True
            return

        # After the dockspace exists -- the builder docks into it -- and
        # before any panel's `begin`, which would otherwise take its
        # position for the frame and only snap into place on the next one.
        #
        # Once, not on every resize. ImGui keeps each dock node's share of
        # its parent and rescales when the root changes, which is the
        # responsive behaviour wanted and what every docking editor does;
        # rebuilding the tree instead threw away any splitter the
        # developer had dragged, every time the window moved.
        self._layout_applied = True
        self._force_layout = False
        self._apply_layout(self._layout, offset)

    @property
    def passthrough_centre(self) -> bool:
        """Whether the dockspace leaves its middle empty."""
        return self._passthrough_centre

    @passthrough_centre.setter
    def passthrough_centre(self, value: bool) -> None:
        """Show or hide whatever is behind the dockspace's middle."""
        self._passthrough_centre = value

    def set_default_layout(
        self, layout: DockLayout | None, *, force: bool = False
    ) -> None:
        """Arrange the panels the next time a frame is built.

        Applied once rather than every frame, so a developer who drags a
        panel somewhere else keeps it there. Without a layout every window
        opens at the same default position, stacked on top of each other,
        which is what an editor with docking enabled and no arrangement
        looks like.

        Args:
            layout: Where each panel goes, or None to leave ImGui's
                defaults alone.
            force: Apply it even over an arrangement restored from the
                settings file. What "Reset Layout" means, and the only
                way to discard a saved one -- installing the default at
                startup must not, or the saved arrangement would never
                survive a restart.
        """
        self._layout = layout
        self._layout_applied = False
        if force:
            self._force_layout = True

    def _apply_layout(self, layout: DockLayout, offset: float = 0.0) -> None:
        """Build the dock tree and assign panels to its regions.

        Args:
            layout: Which panel titles belong in which region.
            offset: How much of the window the dockspace does not cover,
                because the editor's own title bar is above it. The tree
                is built against the space the panels actually get, or
                every ratio is measured against a window that is taller
                than the one they are in.
        """
        internal = imgui.internal
        root = _DOCKSPACE_ID

        internal.dock_builder_remove_node(root)
        internal.dock_builder_add_node(
            root, imgui.internal.DockNodeFlagsPrivate_.dock_space.value
        )
        display = imgui.get_io().display_size
        available = imgui.ImVec2(display.x, max(display.y - offset, 1.0))
        internal.dock_builder_set_node_size(root, available)

        # Split off each side in turn. Every split returns the new node and
        # what is left of the one it came from, and the remainder becomes
        # the thing to split next -- so the centre shrinks as sides are
        # taken, and ends up as the viewport's home.
        centre = root
        regions: dict[str, int] = {}
        display_height = max(float(available.y), 1.0)
        # One row of controls, plus the window's own title bar and its
        # padding above and below. Measured from the live style, because
        # every one of those grows with the UI scale -- a fixed fraction
        # that fits at 1.0 clips the row at 1.25.
        style = imgui.get_style()
        one_row = (
            imgui.get_frame_height()
            + imgui.get_frame_height_with_spacing()
            + style.window_padding.y * 2.0
        )
        # Measured against what is left after the bottom strip, not against
        # the whole window: the top split is taken last, from the remainder,
        # so a ratio of the full height under-allocates it by exactly the
        # bottom's share -- which is what left the Play panel one row short
        # and scrolling.
        remaining = display_height * max(1.0 - layout.bottom_ratio, 0.05)
        top_ratio = (
            layout.top_ratio
            if layout.top_ratio is not None
            else min(one_row / remaining, 0.3)
        )

        for name, direction, ratio in (
            ("left", imgui.Dir.left, layout.left_ratio),
            ("right", imgui.Dir.right, layout.right_ratio),
            ("bottom", imgui.Dir.down, layout.bottom_ratio),
            ("top", imgui.Dir.up, top_ratio),
        ):
            split = internal.dock_builder_split_node(centre, direction, ratio)
            regions[name] = split.id_at_dir
            centre = split.id_at_opposite_dir
        regions["centre"] = centre

        for region, titles in (
            ("left", layout.left),
            ("right", layout.right),
            ("bottom", layout.bottom),
            ("top", layout.top),
            ("centre", layout.centre),
        ):
            for title in titles:
                internal.dock_builder_dock_window(title, regions[region])

        internal.dock_builder_finish(root)
        logger.debug("Applied the default dock layout.")

    def _draw_menu_bar(self) -> None:
        """Draw the panel-visibility menu across the top of the window.

        Skipped when the editor draws its own title bar, which hosts the
        same menu: ImGui's main menu bar always sits at the top edge of
        the viewport, so the two would occupy the same strip.
        """
        if self._title_bar is not None or not self._menus:
            return
        if not imgui.begin_main_menu_bar():
            return
        try:
            for label, draw_items in self._menus:
                if imgui.begin_menu(label, True):
                    try:
                        draw_items()
                    finally:
                        imgui.end_menu()
        finally:
            imgui.end_main_menu_bar()

    def set_settings_file(self, path: Path | None) -> None:
        """Remember the panel arrangement in `path` between runs.

        ImGui's own settings mechanism, which already stores each window's
        dock node, size and collapsed state, and restores them by window
        title. Writing a second one on top of it would be a worse version
        of something that works.

        Must be called **before the first frame**: ImGui reads the file at
        the start of the next `new_frame`, and a layout the dock builder
        has already arranged would be overwritten by what it loads.

        Args:
            path: Where to keep it. The parent directory is created.
                None turns persistence off, which is the default.
        """
        self._settings_file = path
        if path is None:
            self._settings_restored = False
            imgui.set_current_context(self._context)
            imgui.get_io().set_ini_filename("")
            return

        # Recorded before ImGui touches it: afterwards the file exists
        # either way, and whether a *previous* session wrote one is what
        # decides if the shipped arrangement still applies.
        self._settings_restored = path.exists()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                f"Cannot keep the editor layout in {path}: {exc}. "
                f"The arrangement will not survive this session."
            )
            self._settings_restored = False
            return

        imgui.set_current_context(self._context)
        imgui.get_io().set_ini_filename(str(path))
        logger.debug(f"Editor layout remembered in {path}.")

    @property
    def settings_file(self) -> Path | None:
        """Where the panel arrangement is kept, or None."""
        return self._settings_file

    @property
    def settings_restored(self) -> bool:
        """Whether a previous session's arrangement was loaded."""
        return self._settings_restored

    @property
    def toasts(self) -> ToastStack:
        """The short-lived messages shown over the editor."""
        return self._toasts

    @property
    def menus(self) -> tuple[tuple[str, Callable[[], None]], ...]:
        """The menus, in the order they are laid out."""
        return tuple(self._menus)

    def set_menus(self, menus: Sequence[tuple[str, Callable[[], None]]]) -> None:
        """Replace the menus with `menus`.

        The title bar, when there is one, is pointed at the same list, so
        the two never disagree about what the editor offers.

        Args:
            menus: Each a title and something that draws its items.
        """
        self._menus = list(menus)
        if self._title_bar is not None:
            self._title_bar.menus = self._menus

    def draw_panel_menu_items(self) -> None:
        """Draw one toggle per panel, inside an open menu or popup.

        Public because the title bar draws the same items in its own
        popup, and the panel list belongs to the layer rather than to the
        bar.
        """
        for panel in self._panels:
            clicked, _ = imgui.menu_item(panel.title, "", panel.visible)
            if clicked:
                panel.toggle()

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
        self.save_settings()
        if self._renderer is not None:
            self._renderer.release()
            self._renderer = None
        if self._context is not None:
            imgui.destroy_context(self._context)
            self._context = None  # type: ignore[assignment]

    def save_settings(self) -> None:
        """Write the panel arrangement out now, if one is being kept.

        ImGui saves on its own timer -- `io.ini_saving_rate`, five seconds
        by default -- so the last few edits before a clean shutdown would
        otherwise be the ones lost. Does nothing when no settings file is
        set, which is the default.
        """
        if self._settings_file is None or self._context is None:
            return
        try:
            imgui.set_current_context(self._context)
            imgui.save_ini_settings_to_disk(str(self._settings_file))
        except Exception as exc:  # pragma: no cover - a read-only directory
            logger.warning(f"Could not write the editor layout: {exc}")
