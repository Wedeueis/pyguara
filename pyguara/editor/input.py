"""Feed the engine's backend-neutral events into ImGui's IO.

ImGui's own pygame backend is not used, and could not be: it wants raw SDL
structs, while `Window.poll_events()` deliberately hands back engine events
so nothing above the backend boundary imports pygame (issue #9). Translating
here keeps the editor on the right side of that line -- the same reason the
previous ImGui layer was judged to violate it.

Key codes are SDL values, which `pyguara.input.keys` already names as plain
integers, so the keyboard map below is built from that module rather than
from pygame constants.
"""

from __future__ import annotations

from typing import Any

from imgui_bundle import imgui

from pyguara.events.input import (
    KeyDownEvent,
    KeyUpEvent,
    MouseButtonEvent,
    MouseMotionEvent,
    MouseWheelEvent,
    TextInputEvent,
)
from pyguara.input import keys

# Engine button indices (1 left, 2 middle, 3 right) to ImGui's
# (0 left, 1 right, 2 middle). The orders differ, so this cannot be an
# off-by-one adjustment. Wheel indices 4/5 are absent on purpose: they
# arrive as `MouseWheelEvent` instead.
_MOUSE_BUTTONS: dict[int, int] = {1: 0, 2: 2, 3: 1}


def _build_key_map() -> dict[int, Any]:
    """Map SDL key codes to `imgui.Key` values.

    Returns:
        Key code -> ImGui key, for the keys ImGui can act on.
    """
    key_map: dict[int, Any] = {
        keys.TAB: imgui.Key.tab,
        keys.LEFT: imgui.Key.left_arrow,
        keys.RIGHT: imgui.Key.right_arrow,
        keys.UP: imgui.Key.up_arrow,
        keys.DOWN: imgui.Key.down_arrow,
        keys.RETURN: imgui.Key.enter,
        keys.KP_ENTER: imgui.Key.keypad_enter,
        keys.ESCAPE: imgui.Key.escape,
        keys.SPACE: imgui.Key.space,
        keys.BACKSPACE: imgui.Key.backspace,
        keys.DELETE: imgui.Key.delete,
        keys.MINUS: imgui.Key.minus,
        keys.EQUALS: imgui.Key.equal,
        keys.L_BRACKET: imgui.Key.left_bracket,
        keys.R_BRACKET: imgui.Key.right_bracket,
        keys.BACKSLASH: imgui.Key.backslash,
        keys.SEMICOLON: imgui.Key.semicolon,
        keys.QUOTE: imgui.Key.apostrophe,
        keys.COMMA: imgui.Key.comma,
        keys.PERIOD: imgui.Key.period,
        keys.SLASH: imgui.Key.slash,
        keys.TILDE: imgui.Key.grave_accent,
        keys.L_SHIFT: imgui.Key.left_shift,
        keys.R_SHIFT: imgui.Key.right_shift,
        keys.L_CTRL: imgui.Key.left_ctrl,
        keys.R_CTRL: imgui.Key.right_ctrl,
        keys.L_ALT: imgui.Key.left_alt,
        keys.R_ALT: imgui.Key.right_alt,
    }

    # Letters and digits follow ImGui's own contiguous ordering, so they
    # are derived rather than listed: a 36-entry hand-written table is 36
    # chances to typo a pairing no test would catch.
    for offset in range(26):
        key_map[keys.A + offset] = imgui.Key(int(imgui.Key.a) + offset)
    for digit in range(10):
        key_map[keys.NUM_0 + digit] = imgui.Key(int(imgui.Key._0) + digit)
    for index in range(12):
        key_map[keys.F1 + index] = imgui.Key(int(imgui.Key.f1) + index)

    return key_map


_KEY_MAP: dict[int, Any] = _build_key_map()

# Which ImGui modifier each side-specific modifier key contributes. Derived
# from the key events themselves rather than from the events' `modifiers`
# field, which carries SDL `KMOD_*` masks -- reading those would mean
# hardcoding pygame's constants in a module that must not import pygame.
_MODIFIER_KEYS: dict[int, Any] = {
    keys.L_SHIFT: imgui.Key.mod_shift,
    keys.R_SHIFT: imgui.Key.mod_shift,
    keys.L_CTRL: imgui.Key.mod_ctrl,
    keys.R_CTRL: imgui.Key.mod_ctrl,
    keys.L_ALT: imgui.Key.mod_alt,
    keys.R_ALT: imgui.Key.mod_alt,
}


def feed_event(event: object) -> None:
    """Hand one engine event to ImGui.

    Unknown event types are ignored, so this can be given everything
    `poll_events()` produced without filtering first.

    Args:
        event: An engine event, or anything else (ignored).
    """
    io = imgui.get_io()

    if isinstance(event, MouseMotionEvent):
        io.add_mouse_pos_event(float(event.x), float(event.y))
        return

    if isinstance(event, MouseButtonEvent):
        button = _MOUSE_BUTTONS.get(event.button)
        if button is not None:
            io.add_mouse_button_event(button, event.is_down)
        return

    if isinstance(event, MouseWheelEvent):
        io.add_mouse_wheel_event(event.x, event.y)
        return

    if isinstance(event, TextInputEvent):
        for character in event.text:
            io.add_input_character(ord(character))
        return

    if isinstance(event, KeyDownEvent | KeyUpEvent):
        is_down = isinstance(event, KeyDownEvent)
        modifier = _MODIFIER_KEYS.get(event.key_code)
        if modifier is not None:
            io.add_key_event(modifier, is_down)
        imgui_key = _KEY_MAP.get(event.key_code)
        if imgui_key is not None:
            io.add_key_event(imgui_key, is_down)


def wants_mouse() -> bool:
    """Whether ImGui is using the mouse this frame.

    Returns:
        True when the cursor is over an ImGui window or dragging a widget.
    """
    return bool(imgui.get_io().want_capture_mouse)


def wants_keyboard() -> bool:
    """Whether ImGui is using the keyboard this frame.

    Returns:
        True when an ImGui widget has keyboard focus.
    """
    return bool(imgui.get_io().want_capture_keyboard)
