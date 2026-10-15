"""How the editor looks.

Dear ImGui's default style is a debug-overlay style: square corners, thin
separators, a blue that was chosen to be visible rather than to be lived
with. It reads as a diagnostic window bolted onto a game, which is what it
usually is.

An authoring tool is looked at for hours, so this is a deliberate palette
rather than the default one. Three decisions carry most of it:

- **Neutral greys, one accent.** Everything structural is a grey; the
  accent is used only for what is selected or active. A UI that colours
  many things colours nothing.
- **Rounded, with real padding.** Square corners and tight padding are
  what make a dense tool look like a form from 1998.
- **Scaled, not assumed.** A fixed pixel size that is right on a 1280-wide
  window is unreadable on a 4K one. `scale_for` derives a sensible factor
  from the window, and a caller can override it.
"""

from __future__ import annotations

import math
from typing import Any

from imgui_bundle import imgui

ACCENT = (0.26, 0.59, 0.98)
"""The one colour that means "this one". Everything else is a grey."""

REFERENCE_WIDTH = 1536.0
"""The window width at which the UI is drawn at 1:1.

Chosen so a 1080p window lands on 1.25 rather than 1.0: ImGui's built-in
font is a 13px bitmap designed for a debug overlay, and at 1920 wide it is
small enough to squint at. A 1280-wide window stays at 1.0, since below
that the answer is fewer panels rather than smaller text.
"""

MIN_SCALE = 1.0
"""Never shrink. Below this the font stops being legible, and a small
window wants fewer panels rather than smaller text."""

MAX_SCALE = 3.0
"""Beyond this the chrome eats the screen on any display sold today."""


def scale_for(width: int, height: int) -> float:
    """Return a UI scale that keeps the editor legible at `width`.

    Derived from the window rather than from the OS's DPI setting, which
    SDL does not report reliably across the platforms this runs on -- and
    which is the wrong question anyway: what matters is how much room the
    panels have, not how dense the pixels are.

    Args:
        width: The window width in pixels.
        height: The window height in pixels, used only to avoid scaling up
            a window that is wide and short.

    Returns:
        A factor between `MIN_SCALE` and `MAX_SCALE`.
    """
    if width <= 0 or height <= 0:
        return MIN_SCALE
    # Steps of a quarter, so dragging a window across a monitor boundary
    # does not reflow the layout on every pixel. Rounded half-up by hand:
    # `round` is banker's rounding, and an exact 1.125 -- which 1920x1080
    # produces -- would go *down* to 1.0, which is the case this exists to
    # fix.
    raw = min(width / REFERENCE_WIDTH, height / (REFERENCE_WIDTH * 0.5625))
    stepped = math.floor(raw * 4 + 0.5) / 4
    return max(MIN_SCALE, min(MAX_SCALE, stepped))


def apply_theme(style: Any | None = None) -> None:
    """Apply the editor's dark theme to an ImGui style.

    Args:
        style: The style to write to. Defaults to the current context's.
    """
    style = style if style is not None else imgui.get_style()

    _apply_metrics(style)
    _apply_colours(style)


def _apply_metrics(style: Any) -> None:
    """Set the rounding, padding and border widths.

    Args:
        style: The style to write to.
    """
    style.window_rounding = 6.0
    style.child_rounding = 6.0
    style.frame_rounding = 4.0
    style.popup_rounding = 6.0
    style.scrollbar_rounding = 8.0
    style.grab_rounding = 4.0
    style.tab_rounding = 4.0

    style.window_padding = imgui.ImVec2(10.0, 10.0)
    style.frame_padding = imgui.ImVec2(8.0, 4.0)
    style.item_spacing = imgui.ImVec2(8.0, 6.0)
    style.item_inner_spacing = imgui.ImVec2(6.0, 5.0)
    style.indent_spacing = 20.0
    style.scrollbar_size = 12.0
    style.grab_min_size = 10.0

    # Borders only where they separate: a border on every frame is the
    # 1998 look, a border on a window and a popup is structure.
    style.window_border_size = 1.0
    style.child_border_size = 1.0
    style.popup_border_size = 1.0
    style.frame_border_size = 0.0
    style.tab_border_size = 0.0

    style.window_title_align = imgui.ImVec2(0.0, 0.5)
    style.window_menu_button_position = imgui.Dir.none


def _apply_colours(style: Any) -> None:
    """Set the palette.

    Written through `set_color_` rather than by assigning into
    `style.colors`: this binding exposes the colour table as a reader
    (`color_`) and a writer, not as a mutable sequence.

    Args:
        style: The style to write to.
    """
    c = imgui.Col_

    def rgba(r: float, g: float, b: float, a: float = 1.0) -> Any:
        return imgui.ImVec4(r, g, b, a)

    def paint(slot: Any, colour: Any) -> None:
        style.set_color_(slot.value, colour)

    accent = rgba(*ACCENT)
    accent_dim = rgba(ACCENT[0], ACCENT[1], ACCENT[2], 0.45)
    accent_hover = rgba(
        min(ACCENT[0] + 0.08, 1.0),
        min(ACCENT[1] + 0.08, 1.0),
        min(ACCENT[2] + 0.04, 1.0),
    )

    paint(c.text, rgba(0.90, 0.91, 0.93))
    paint(c.text_disabled, rgba(0.48, 0.50, 0.54))

    paint(c.window_bg, rgba(0.13, 0.14, 0.16))
    paint(c.child_bg, rgba(0.11, 0.12, 0.14))
    paint(c.popup_bg, rgba(0.10, 0.11, 0.13, 0.98))
    paint(c.border, rgba(0.22, 0.23, 0.26))
    paint(c.border_shadow, rgba(0.0, 0.0, 0.0, 0.0))

    paint(c.frame_bg, rgba(0.18, 0.19, 0.22))
    paint(c.frame_bg_hovered, rgba(0.24, 0.25, 0.29))
    paint(c.frame_bg_active, rgba(0.28, 0.30, 0.35))

    paint(c.title_bg, rgba(0.10, 0.11, 0.13))
    paint(c.title_bg_active, rgba(0.15, 0.16, 0.19))
    paint(c.title_bg_collapsed, rgba(0.10, 0.11, 0.13, 0.75))
    paint(c.menu_bar_bg, rgba(0.15, 0.16, 0.19))

    paint(c.scrollbar_bg, rgba(0.11, 0.12, 0.14))
    paint(c.scrollbar_grab, rgba(0.28, 0.30, 0.34))
    paint(c.scrollbar_grab_hovered, rgba(0.35, 0.37, 0.42))
    paint(c.scrollbar_grab_active, rgba(0.42, 0.44, 0.50))

    paint(c.check_mark, accent)
    paint(c.slider_grab, rgba(0.38, 0.40, 0.46))
    paint(c.slider_grab_active, accent)

    paint(c.button, rgba(0.22, 0.23, 0.27))
    paint(c.button_hovered, rgba(0.29, 0.31, 0.36))
    paint(c.button_active, accent)

    paint(c.header, rgba(0.22, 0.24, 0.28))
    paint(c.header_hovered, rgba(0.28, 0.30, 0.35))
    paint(c.header_active, accent_dim)

    paint(c.separator, rgba(0.22, 0.23, 0.26))
    paint(c.separator_hovered, accent_dim)
    paint(c.separator_active, accent)

    paint(c.resize_grip, rgba(0.0, 0.0, 0.0, 0.0))
    paint(c.resize_grip_hovered, accent_dim)
    paint(c.resize_grip_active, accent)

    paint(c.tab, rgba(0.15, 0.16, 0.19))
    paint(c.tab_hovered, rgba(0.26, 0.28, 0.33))
    paint(c.tab_selected, rgba(0.21, 0.23, 0.27))
    paint(c.tab_dimmed, rgba(0.12, 0.13, 0.15))
    paint(c.tab_dimmed_selected, rgba(0.17, 0.18, 0.21))
    # The strip marking the selected tab -- the one place a flat dark
    # theme needs the accent to say where you are.
    paint(c.tab_selected_overline, accent)
    paint(c.tab_dimmed_selected_overline, accent_dim)

    paint(c.docking_preview, accent_dim)
    paint(c.docking_empty_bg, rgba(0.10, 0.10, 0.12))

    paint(c.plot_lines, rgba(0.70, 0.72, 0.76))
    paint(c.plot_lines_hovered, accent_hover)
    paint(c.plot_histogram, accent)
    paint(c.plot_histogram_hovered, accent_hover)

    paint(c.table_header_bg, rgba(0.17, 0.18, 0.21))
    paint(c.table_border_strong, rgba(0.24, 0.25, 0.29))
    paint(c.table_border_light, rgba(0.19, 0.20, 0.23))
    paint(c.table_row_bg, rgba(0.0, 0.0, 0.0, 0.0))
    paint(c.table_row_bg_alt, rgba(1.0, 1.0, 1.0, 0.025))

    paint(c.text_selected_bg, accent_dim)
    paint(c.drag_drop_target, accent)
    paint(c.nav_cursor, accent)
    paint(c.modal_window_dim_bg, rgba(0.05, 0.05, 0.06, 0.60))
