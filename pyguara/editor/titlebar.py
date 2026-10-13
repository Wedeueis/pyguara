"""A title bar the editor draws itself.

What Godot 4 and VS Code do on Windows, and the reason they do not look
like a 1998 dialog: the OS frame is removed and the application draws the
bar, so the title, the window buttons and the application's own chrome
share one surface and one palette.

It is **opt-in**, through `display.borderless`. Two reasons for that
rather than making it the default:

- It only works where the backend offers window controls. A backend that
  cannot move or maximise its own window is fine; it just keeps the OS
  bar.
- Removing the OS frame also removes the OS's resize edges. A borderless
  window is only usable if the application provides its own, and the
  `resizable` flag is what lets the window manager keep doing that.

Dragging moves the window by a **delta** rather than to an absolute
position. A window manager may place a window somewhere other than asked
-- WSLg offsets by the decoration it would otherwise have drawn -- so
reading a position back and setting an absolute one accumulates that
error on every frame of a drag, and the window walks away from the
cursor.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from imgui_bundle import imgui

from pyguara.log import get_logger

logger = get_logger(__name__)

HEIGHT = 30.0
"""The bar's height in unscaled pixels, multiplied by the UI scale."""

BUTTON_WIDTH = 44.0
"""Width of each window button, unscaled. Wider than tall on purpose:
these are the targets a user hits without looking."""

ICON_SIZE = 10.0
"""How large a window button's icon is drawn, unscaled."""

MENU_LABEL = "Panels"
"""The menu the bar opens on the left. One menu, so it is a labelled
button with a popup rather than a menu bar -- which would be a second row
and defeat the point of drawing the bar ourselves."""

_CLOSE_HOVER = imgui.ImVec4(0.78, 0.22, 0.24, 1.0)
_BUTTON_HOVER = imgui.ImVec4(1.0, 1.0, 1.0, 0.10)
_TRANSPARENT = imgui.ImVec4(0.0, 0.0, 0.0, 0.0)


class TitleBar:
    """Draws the window's title and its minimise/maximise/close buttons."""

    def __init__(
        self,
        title: str,
        chrome: Any,
        *,
        menu: Callable[[], None] | None = None,
    ) -> None:
        """Initialize the bar.

        Args:
            title: What to show in the middle.
            chrome: Something satisfying `IWindowChrome`.
            menu: Draws the contents of the bar's menu popup. Set by the
                editor layer, which owns the panel list. None draws no
                menu button at all.
        """
        self._title = title
        self._chrome = chrome
        self._dragging = False
        self._close_requested = False
        self.menu = menu
        self._menu_width = 0.0

    @property
    def title(self) -> str:
        """The text shown in the bar."""
        return self._title

    @title.setter
    def title(self, value: str) -> None:
        """Change the text shown in the bar."""
        self._title = value

    @property
    def close_requested(self) -> bool:
        """Whether the close button has been pressed.

        Read and acted on by whoever owns the application loop; the bar
        itself does not quit, because what a close means -- prompt to
        save, close a document, exit -- is not its decision.
        """
        return self._close_requested

    @property
    def dragging(self) -> bool:
        """Whether the window is being dragged by the bar."""
        return self._dragging

    def height(self) -> float:
        """Return the bar's height at the current UI scale.

        Returns:
            Height in pixels.
        """
        return HEIGHT * max(imgui.get_style().font_scale_main, 1.0)

    def draw(self, width: float) -> float:
        """Draw the bar across the top of the window.

        Args:
            width: The window width in pixels.

        Returns:
            The height consumed, so a caller can offset whatever comes
            next.
        """
        height = self.height()
        scale = max(imgui.get_style().font_scale_main, 1.0)

        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(width, height))
        imgui.push_style_var(imgui.StyleVar_.window_rounding, 0.0)
        imgui.push_style_var(imgui.StyleVar_.window_border_size, 0.0)
        imgui.push_style_var(
            imgui.StyleVar_.window_padding, imgui.ImVec2(8.0 * scale, 0.0)
        )
        # The same tone the menu bar gets when the OS draws the frame, so
        # the strip reads as chrome rather than as one more panel.
        imgui.push_style_color(
            imgui.Col_.window_bg, imgui.get_style().color_(imgui.Col_.menu_bar_bg)
        )

        flags = (
            imgui.WindowFlags_.no_decoration.value
            | imgui.WindowFlags_.no_move.value
            | imgui.WindowFlags_.no_saved_settings.value
            | imgui.WindowFlags_.no_bring_to_front_on_focus.value
            | imgui.WindowFlags_.no_docking.value
            | imgui.WindowFlags_.no_scrollbar.value
        )

        imgui.begin("##titlebar", None, flags)
        try:
            self._draw_menu(height, scale)
            self._draw_title(width, height)
            self._draw_buttons(width, height, scale)
            self._handle_drag(width, scale)
        finally:
            imgui.end()
            imgui.pop_style_color()
            imgui.pop_style_var(3)

        return height

    def _draw_menu(self, height: float, scale: float) -> None:
        """Draw the menu button at the left end of the bar.

        The menu lives in the bar rather than in a row below it, which is
        what makes this one strip of chrome instead of two -- the whole
        reason for drawing the bar at all.

        Args:
            height: The bar height.
            scale: The UI scale.
        """
        if self.menu is None:
            self._menu_width = 0.0
            return

        width = imgui.calc_text_size(MENU_LABEL).x + 24.0 * scale
        self._menu_width = width

        imgui.set_cursor_pos(imgui.ImVec2(0.0, 0.0))
        imgui.push_style_var(imgui.StyleVar_.frame_rounding, 0.0)
        imgui.push_style_color(imgui.Col_.button, _TRANSPARENT)
        imgui.push_style_color(imgui.Col_.button_hovered, _BUTTON_HOVER)
        imgui.push_style_color(imgui.Col_.button_active, _BUTTON_HOVER)
        try:
            if imgui.button(MENU_LABEL, imgui.ImVec2(width, height)):
                imgui.open_popup("##titlebar_menu")
            if imgui.begin_popup("##titlebar_menu"):
                try:
                    self.menu()
                finally:
                    imgui.end_popup()
        finally:
            imgui.pop_style_color(3)
            imgui.pop_style_var()

    def _draw_title(self, width: float, height: float) -> None:
        """Centre the title text vertically and horizontally.

        Args:
            width: The window width.
            height: The bar height.
        """
        text_size = imgui.calc_text_size(self._title)
        imgui.set_cursor_pos(
            imgui.ImVec2(
                (width - text_size.x) * 0.5,
                (height - text_size.y) * 0.5,
            )
        )
        imgui.text_disabled(self._title)

    def _draw_buttons(self, width: float, height: float, scale: float) -> None:
        """Draw minimise, maximise/restore and close, right-aligned.

        The icons are drawn as lines rather than written as text. ImGui's
        built-in font carries Basic Latin and nothing else, so the glyphs
        this wants -- U+2715, U+25A1 -- come out as the atlas's fallback
        box. Three strokes are cheaper than shipping a font, and scale
        cleanly with the UI.

        Args:
            width: The window width.
            height: The bar height.
            scale: The UI scale.
        """
        button_width = BUTTON_WIDTH * scale
        imgui.push_style_var(imgui.StyleVar_.frame_rounding, 0.0)
        imgui.push_style_color(imgui.Col_.button, _TRANSPARENT)
        try:
            # Right to left, so each button's x is independent of the
            # widths of the ones before it.
            specs = (
                ("close", self._close, _CLOSE_HOVER),
                ("maximize", self._toggle_maximize, _BUTTON_HOVER),
                ("minimize", self._minimize, _BUTTON_HOVER),
            )
            for index, (icon, action, hover) in enumerate(specs):
                imgui.set_cursor_pos(
                    imgui.ImVec2(width - button_width * (index + 1), 0.0)
                )
                imgui.push_style_color(imgui.Col_.button_hovered, hover)
                imgui.push_style_color(imgui.Col_.button_active, hover)
                try:
                    pressed = imgui.button(
                        f"##{icon}", imgui.ImVec2(button_width, height)
                    )
                finally:
                    imgui.pop_style_color(2)
                self._draw_icon(icon, scale)
                if pressed:
                    action()
        finally:
            imgui.pop_style_color()
            imgui.pop_style_var()

    def _draw_icon(self, icon: str, scale: float) -> None:
        """Stroke one window-button icon over the button just submitted.

        Args:
            icon: Which of "minimize", "maximize" or "close".
            scale: The UI scale, which the stroke width follows.
        """
        draw_list = imgui.get_window_draw_list()
        low = imgui.get_item_rect_min()
        high = imgui.get_item_rect_max()
        centre_x = (low.x + high.x) * 0.5
        centre_y = (low.y + high.y) * 0.5
        half = ICON_SIZE * scale * 0.5
        thickness = max(1.0, scale)
        colour = imgui.get_color_u32(imgui.Col_.text)

        if icon == "minimize":
            draw_list.add_line(
                imgui.ImVec2(centre_x - half, centre_y),
                imgui.ImVec2(centre_x + half, centre_y),
                colour,
                thickness,
            )
            return

        if icon == "close":
            draw_list.add_line(
                imgui.ImVec2(centre_x - half, centre_y - half),
                imgui.ImVec2(centre_x + half, centre_y + half),
                colour,
                thickness,
            )
            draw_list.add_line(
                imgui.ImVec2(centre_x + half, centre_y - half),
                imgui.ImVec2(centre_x - half, centre_y + half),
                colour,
                thickness,
            )
            return

        if not self._maximized():
            draw_list.add_rect(
                imgui.ImVec2(centre_x - half, centre_y - half),
                imgui.ImVec2(centre_x + half, centre_y + half),
                colour,
                0.0,
                thickness,
            )
            return

        # Restore: the window in front, and the one it would go back to
        # peeking out behind it -- the same two-square idiom every desktop
        # uses, so it needs no explaining.
        offset = half * 0.5
        draw_list.add_rect(
            imgui.ImVec2(centre_x - half + offset, centre_y - half - offset),
            imgui.ImVec2(centre_x + half + offset, centre_y + half - offset),
            colour,
            0.0,
            thickness,
        )
        draw_list.add_rect_filled(
            imgui.ImVec2(centre_x - half, centre_y - half + offset),
            imgui.ImVec2(centre_x + half, centre_y + half + offset),
            imgui.get_color_u32(imgui.Col_.window_bg),
        )
        draw_list.add_rect(
            imgui.ImVec2(centre_x - half, centre_y - half + offset),
            imgui.ImVec2(centre_x + half, centre_y + half + offset),
            colour,
            0.0,
            thickness,
        )

    def _handle_drag(self, width: float, scale: float) -> None:
        """Move the window while the bar is dragged.

        The drag region excludes the menu button and the window buttons,
        so pressing close and sliding a pixel does not also shove the
        window.

        Args:
            width: The window width.
            scale: The UI scale.
        """
        buttons_start = width - BUTTON_WIDTH * scale * 3

        if imgui.is_mouse_released(imgui.MouseButton_.left):
            self._dragging = False

        if not self._dragging:
            hovered = imgui.is_window_hovered(
                imgui.HoveredFlags_.allow_when_blocked_by_active_item.value
            )
            pressed = imgui.is_mouse_clicked(imgui.MouseButton_.left)
            mouse_x = imgui.get_io().mouse_pos.x
            over_buttons = mouse_x >= buttons_start or mouse_x < self._menu_width
            if hovered and pressed and not over_buttons:
                self._dragging = True
                # A double-click on the bar maximises, which is what every
                # window manager does and what a user will try first.
                if imgui.is_mouse_double_clicked(imgui.MouseButton_.left):
                    self._dragging = False
                    self._toggle_maximize()
            return

        if not imgui.is_mouse_down(imgui.MouseButton_.left):
            self._dragging = False
            return

        delta = imgui.get_io().mouse_delta
        if delta.x or delta.y:
            self._move(int(delta.x), int(delta.y))

    # ----------------------------------------------------------------
    # Window actions, each tolerant of a backend that cannot do it
    # ----------------------------------------------------------------

    def _maximized(self) -> bool:
        """Whether the window is maximised, as far as the backend knows."""
        try:
            return bool(self._chrome.is_maximized)
        except Exception:  # pragma: no cover - depends on the backend
            return False

    def _minimize(self) -> None:
        """Iconify, logging rather than raising if the backend cannot."""
        self._attempt("minimize", self._chrome.minimize)

    def _toggle_maximize(self) -> None:
        """Maximise, or restore if already maximised."""
        if self._maximized():
            self._attempt("restore", self._chrome.restore)
        else:
            self._attempt("maximize", self._chrome.maximize)

    def _move(self, dx: int, dy: int) -> None:
        """Move the window by a delta."""
        self._attempt("move", lambda: self._chrome.move_by(dx, dy))

    def _close(self) -> None:
        """Ask the window to close, and record that it was asked.

        Both, because the two answer different questions: the backend runs
        the application's real shutdown, and the flag lets whoever owns the
        loop see that a close is pending -- to prompt about unsaved work,
        say -- without having to intercept the event.
        """
        self._close_requested = True
        self._attempt("close", lambda: self._chrome.request_close())

    @staticmethod
    def _attempt(name: str, action: Any) -> None:
        """Run a window action, logging a failure rather than raising.

        A window manager that refuses one of these must not take the
        editor's frame down with it.

        Args:
            name: What was attempted, for the log.
            action: The call to make.
        """
        try:
            action()
        except Exception as exc:  # pragma: no cover - depends on the WM
            logger.debug(f"Window {name} failed: {exc}")
