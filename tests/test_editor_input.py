"""Engine events -> ImGui IO.

ImGui's own pygame backend is unusable here by design: it wants raw SDL
structs, while `Window.poll_events()` hands back engine events so nothing
above the backend boundary imports pygame (issue #9). These pin the
translation that replaces it, including the two mappings most likely to
rot: the mouse-button reordering and the derived keyboard table.
"""

from __future__ import annotations

from typing import Any

import pytest

from pyguara.editor import input as editor_input
from pyguara.events.input import (
    KeyDownEvent,
    KeyUpEvent,
    MouseButtonEvent,
    MouseMotionEvent,
    MouseWheelEvent,
    TextInputEvent,
)
from pyguara.input import keys

imgui_bundle = pytest.importorskip("imgui_bundle")
imgui = imgui_bundle.imgui


def _frame(io: Any) -> None:
    """Run one complete ImGui frame so queued input is applied to IO."""
    imgui.new_frame()
    imgui.end_frame()


@pytest.mark.unit
class TestMouse:
    def test_motion_sets_the_cursor_position(self, imgui_ctx: Any) -> None:
        editor_input.feed_event(MouseMotionEvent(x=120, y=80, rel_x=1, rel_y=1))
        _frame(imgui_ctx)
        assert (imgui_ctx.mouse_pos.x, imgui_ctx.mouse_pos.y) == (120.0, 80.0)

    @pytest.mark.parametrize(
        ("engine_button", "imgui_index"),
        [(1, 0), (3, 1), (2, 2)],
        ids=["left", "right", "middle"],
    )
    def test_button_indices_are_reordered_not_offset(
        self, imgui_ctx: Any, engine_button: int, imgui_index: int
    ) -> None:
        """The engine numbers 1 left / 2 middle / 3 right; ImGui numbers
        0 left / 1 right / 2 middle. Middle and right swap, so this is a
        remap and an off-by-one 'fix' would silently cross them."""
        editor_input.feed_event(
            MouseButtonEvent(button=engine_button, x=0, y=0, is_down=True)
        )
        _frame(imgui_ctx)
        assert imgui.is_mouse_down(imgui_index) is True

    def test_button_release_clears_the_button(self, imgui_ctx: Any) -> None:
        editor_input.feed_event(MouseButtonEvent(button=1, x=0, y=0, is_down=True))
        _frame(imgui_ctx)
        editor_input.feed_event(MouseButtonEvent(button=1, x=0, y=0, is_down=False))
        _frame(imgui_ctx)
        assert imgui.is_mouse_down(0) is False

    def test_an_unknown_button_is_ignored(self, imgui_ctx: Any) -> None:
        """Wheel indices 4/5 arrive as MouseWheelEvent instead, so they
        must not land on an ImGui button."""
        editor_input.feed_event(MouseButtonEvent(button=4, x=0, y=0, is_down=True))
        _frame(imgui_ctx)
        assert not any(imgui.is_mouse_down(index) for index in (0, 1, 2))

    def test_wheel_reaches_both_axes(self, imgui_ctx: Any) -> None:
        """Read *inside* the frame: unlike `mouse_pos`, which is state,
        the wheel is a per-frame delta that ImGui clears at `end_frame()`."""
        editor_input.feed_event(MouseWheelEvent(x=-2.0, y=3.0))
        imgui.new_frame()
        try:
            assert (imgui_ctx.mouse_wheel_h, imgui_ctx.mouse_wheel) == (-2.0, 3.0)
        finally:
            imgui.end_frame()

    def test_wheel_delta_does_not_persist_into_the_next_frame(
        self, imgui_ctx: Any
    ) -> None:
        editor_input.feed_event(MouseWheelEvent(x=0.0, y=1.0))
        _frame(imgui_ctx)
        imgui.new_frame()
        try:
            assert imgui_ctx.mouse_wheel == 0.0
        finally:
            imgui.end_frame()


@pytest.mark.unit
class TestKeyboard:
    def test_a_mapped_key_goes_down_and_up(self, imgui_ctx: Any) -> None:
        editor_input.feed_event(KeyDownEvent(key_code=keys.SPACE))
        _frame(imgui_ctx)
        assert imgui.is_key_down(imgui.Key.space) is True

        editor_input.feed_event(KeyUpEvent(key_code=keys.SPACE))
        _frame(imgui_ctx)
        assert imgui.is_key_down(imgui.Key.space) is False

    @pytest.mark.parametrize(
        ("code", "key_name"),
        [
            (keys.A, "a"),
            (keys.Z, "z"),
            (keys.NUM_0, "_0"),
            (keys.NUM_9, "_9"),
            (keys.F1, "f1"),
            (keys.F12, "f12"),
        ],
    )
    def test_derived_ranges_land_on_the_right_key(
        self, imgui_ctx: Any, code: int, key_name: str
    ) -> None:
        """Letters, digits and function keys are *derived* from ImGui's
        contiguous ordering rather than listed, so these pin the ends and
        the middle of each range against ImGui's own names."""
        editor_input.feed_event(KeyDownEvent(key_code=code))
        _frame(imgui_ctx)
        assert imgui.is_key_down(getattr(imgui.Key, key_name)) is True

    def test_a_modifier_key_sets_the_modifier(self, imgui_ctx: Any) -> None:
        """Modifier state is derived from the modifier keys themselves, not
        from the event's `modifiers` field -- that carries SDL KMOD masks,
        and reading them would mean hardcoding pygame constants in a module
        that must not import pygame."""
        editor_input.feed_event(KeyDownEvent(key_code=keys.L_CTRL))
        _frame(imgui_ctx)
        assert imgui_ctx.key_ctrl is True

        editor_input.feed_event(KeyUpEvent(key_code=keys.L_CTRL))
        _frame(imgui_ctx)
        assert imgui_ctx.key_ctrl is False

    def test_right_hand_modifier_sets_the_same_flag(self, imgui_ctx: Any) -> None:
        editor_input.feed_event(KeyDownEvent(key_code=keys.R_SHIFT))
        _frame(imgui_ctx)
        assert imgui_ctx.key_shift is True

    def test_an_unmapped_key_is_dropped(self, imgui_ctx: Any) -> None:
        editor_input.feed_event(KeyDownEvent(key_code=987654321))
        _frame(imgui_ctx)  # must not raise


@pytest.mark.unit
class TestText:
    def test_text_input_queues_characters(self, imgui_ctx: Any) -> None:
        editor_input.feed_event(TextInputEvent(text="hi"))
        _frame(imgui_ctx)
        # The queue is drained by the frame; reaching it without raising,
        # with the event accepted, is what this pins.

    def test_a_foreign_object_is_ignored(self, imgui_ctx: Any) -> None:
        editor_input.feed_event(object())
        _frame(imgui_ctx)  # must not raise


@pytest.mark.unit
class TestCaptureQueries:
    def test_capture_flags_are_readable(self, imgui_ctx: Any) -> None:
        _frame(imgui_ctx)
        assert isinstance(editor_input.wants_mouse(), bool)
        assert isinstance(editor_input.wants_keyboard(), bool)

    def test_hovering_a_window_captures_the_mouse(self, imgui_ctx: Any) -> None:
        """The real reason `wants_mouse()` exists: with the cursor over an
        editor window the game must not also act on the click."""
        imgui.new_frame()
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(400.0, 300.0))
        imgui.begin("Panel")
        imgui.text("content")
        imgui.end()
        imgui.end_frame()

        editor_input.feed_event(MouseMotionEvent(x=100, y=100, rel_x=0, rel_y=0))
        imgui.new_frame()
        imgui.set_next_window_pos(imgui.ImVec2(0.0, 0.0))
        imgui.set_next_window_size(imgui.ImVec2(400.0, 300.0))
        imgui.begin("Panel")
        imgui.text("content")
        imgui.end()
        imgui.end_frame()

        assert editor_input.wants_mouse() is True
