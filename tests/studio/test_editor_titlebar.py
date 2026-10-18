"""The title bar the editor draws when the window has no frame of its own.

Run against a stub chrome rather than a real window: what is worth locking
is that a click on a button reaches the right window action, that a drag
moves by a delta, and that a backend refusing an action does not take the
frame down. None of that needs SDL, and the parts that would -- whether
the window manager honours a move -- cannot be asserted here anyway.
"""

from __future__ import annotations

import pytest

from pyguara.di.container import DIContainer
from pyguara.events.input import MouseButtonEvent

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.graphics.protocols import IWindowChrome  # noqa: E402
from pyguara.studio.layer import EditorLayer  # noqa: E402
from pyguara.studio.titlebar import BUTTON_WIDTH, HEIGHT, TitleBar  # noqa: E402

WIDTH = 1280
"""Narrow enough to stay at a UI scale of 1.0, so the pixel positions the
button tests click on are the unscaled ones."""

HEIGHT_PX = 720


class FakeChrome:
    """Records what was asked of the window."""

    def __init__(self) -> None:
        self.calls: list[object] = []
        self.maximized = False

    def minimize(self) -> None:
        self.calls.append("minimize")

    def maximize(self) -> None:
        self.calls.append("maximize")
        self.maximized = True

    def restore(self) -> None:
        self.calls.append("restore")
        self.maximized = False

    def request_close(self) -> None:
        self.calls.append("close")

    @property
    def is_maximized(self) -> bool:
        return self.maximized

    def begin_move(self) -> None:
        self.calls.append("begin_move")

    def move_by(self, dx: int, dy: int) -> None:
        self.calls.append(("move", dx, dy))

    def end_move(self) -> None:
        self.calls.append("end_move")


class RefusingChrome(FakeChrome):
    """A backend whose window manager says no to everything."""

    def minimize(self) -> None:
        raise RuntimeError("no")

    def maximize(self) -> None:
        raise RuntimeError("no")

    def restore(self) -> None:
        raise RuntimeError("no")

    def request_close(self) -> None:
        raise RuntimeError("no")

    def begin_move(self) -> None:
        raise RuntimeError("no")

    def move_by(self, dx: int, dy: int) -> None:
        raise RuntimeError("no")

    def end_move(self) -> None:
        raise RuntimeError("no")

    @property
    def is_maximized(self) -> bool:
        raise RuntimeError("no")


def _layer(bar: TitleBar | None = None) -> EditorLayer:
    """A renderer-less layer, optionally with a title bar."""
    layer = EditorLayer(DIContainer(), renderer_factory=None, panels=[])
    if bar is not None:
        layer.set_title_bar(bar)
    return layer


def _click_at(layer: EditorLayer, x: float, y: float) -> None:
    """Press and release the left button at `x, y` across three frames.

    Three because ImGui settles a widget over two frames before it will
    report a click on it, and the release has to land on a frame of its
    own for the button to fire.
    """
    io = imgui.get_io()
    layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
    io.add_mouse_pos_event(x, y)
    layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
    io.add_mouse_button_event(0, True)
    layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
    io.add_mouse_button_event(0, False)
    layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)


@pytest.mark.unit
class TestDrawing:
    def test_the_bar_adds_geometry_to_the_frame(self) -> None:
        plain = _layer()
        try:
            plain.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            without = plain.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            bare = without.total_vtx_count
        finally:
            plain.release()

        layer = _layer(TitleBar("Studio", FakeChrome()))
        try:
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            with_bar = layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert with_bar.total_vtx_count > bare
        finally:
            layer.release()

    def test_the_height_follows_the_ui_scale(self) -> None:
        layer = _layer(TitleBar("Studio", FakeChrome()))
        bar = layer.title_bar
        assert bar is not None
        try:
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert bar.height() == pytest.approx(HEIGHT)
            # A 1080p window scales the chrome up, and the bar with it.
            layer.build_frame(1920, 1080, dt=1 / 60)
            assert bar.height() == pytest.approx(HEIGHT * layer.ui_scale)
            assert layer.ui_scale > 1.0
        finally:
            layer.release()

    def test_removing_the_bar_returns_the_space(self) -> None:
        layer = _layer(TitleBar("Studio", FakeChrome()))
        try:
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            layer.set_title_bar(None)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert layer.title_bar is None
        finally:
            layer.release()

    def test_the_title_is_what_was_set(self) -> None:
        bar = TitleBar("Studio", FakeChrome())
        assert bar.title == "Studio"
        bar.title = "Studio - quintal_cerrado"
        assert bar.title == "Studio - quintal_cerrado"

    def test_the_layer_lends_the_bar_its_menus(self) -> None:
        bar = TitleBar("Studio", FakeChrome())
        layer = _layer(bar)
        try:
            assert [label for label, _ in bar.menus] == ["Panels"]
        finally:
            layer.release()

    def test_menus_passed_in_are_left_alone(self) -> None:
        def mine() -> None:  # pragma: no cover - never drawn here
            pass

        bar = TitleBar("Studio", FakeChrome(), menus=[("Mine", mine)])
        layer = _layer(bar)
        try:
            assert [label for label, _ in bar.menus] == ["Mine"]
        finally:
            layer.release()

    def test_replacing_the_layer_menus_reaches_the_bar(self) -> None:
        """One source: a bar showing a different set from the main menu
        bar would be two answers to what the editor offers."""

        def mine() -> None:  # pragma: no cover - never drawn here
            pass

        bar = TitleBar("Studio", FakeChrome())
        layer = _layer(bar)
        try:
            layer.set_menus([("Scene", mine), ("Edit", mine)])
            assert [label for label, _ in bar.menus] == ["Scene", "Edit"]
        finally:
            layer.release()


@pytest.mark.unit
class TestButtons:
    def test_close_asks_the_window_and_records_it(self) -> None:
        chrome = FakeChrome()
        bar = TitleBar("Studio", chrome)
        layer = _layer(bar)
        try:
            assert not bar.close_requested
            _click_at(layer, WIDTH - BUTTON_WIDTH * 0.5, HEIGHT * 0.5)
            assert bar.close_requested
            assert "close" in chrome.calls
        finally:
            layer.release()

    def test_the_middle_button_maximizes_then_restores(self) -> None:
        chrome = FakeChrome()
        layer = _layer(TitleBar("Studio", chrome))
        try:
            middle = WIDTH - BUTTON_WIDTH * 1.5
            _click_at(layer, middle, HEIGHT * 0.5)
            assert chrome.calls == ["maximize"]
            _click_at(layer, middle, HEIGHT * 0.5)
            assert chrome.calls == ["maximize", "restore"]
        finally:
            layer.release()

    def test_the_left_button_minimizes(self) -> None:
        chrome = FakeChrome()
        layer = _layer(TitleBar("Studio", chrome))
        try:
            _click_at(layer, WIDTH - BUTTON_WIDTH * 2.5, HEIGHT * 0.5)
            assert chrome.calls == ["minimize"]
        finally:
            layer.release()

    def test_a_click_in_the_middle_of_the_bar_presses_nothing(self) -> None:
        chrome = FakeChrome()
        layer = _layer(TitleBar("Studio", chrome))
        try:
            _click_at(layer, WIDTH * 0.5, HEIGHT * 0.5)
            assert not any(call == "minimize" for call in chrome.calls)
            assert "close" not in chrome.calls
        finally:
            layer.release()


@pytest.mark.unit
class TestDragging:
    def test_a_drag_moves_the_window_by_the_delta(self) -> None:
        chrome = FakeChrome()
        bar = TitleBar("Studio", chrome)
        layer = _layer(bar)
        io = imgui.get_io()
        try:
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_pos_event(400.0, HEIGHT * 0.5)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_button_event(0, True)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert bar.dragging
            io.add_mouse_pos_event(430.0, HEIGHT * 0.5 + 12.0)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert ("move", 30, 12) in chrome.calls
            io.add_mouse_button_event(0, False)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert not bar.dragging
        finally:
            layer.release()

    def test_the_window_tracks_the_cursor_one_to_one(self) -> None:
        """The position SDL reports is relative to the window being moved,
        so a drag that moves by the frame-to-frame delta cancels itself:
        measured, the window tracked at exactly half speed, stepping on
        alternate frames. Measuring from the grab point instead is
        self-correcting, and this is what that is worth."""
        chrome = FakeChrome()
        bar = TitleBar("Studio", chrome)
        layer = _layer(bar)
        io = imgui.get_io()
        # The cursor in screen space, and where the window starts.
        cursor_x = 500.0
        window_x = 0.0
        try:

            def frame() -> None:
                io.add_mouse_pos_event(cursor_x - window_x, HEIGHT * 0.5)
                layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)

            frame()
            frame()
            io.add_mouse_button_event(0, True)
            frame()
            assert bar.dragging

            for _ in range(6):
                cursor_x += 10.0
                frame()
                for call in chrome.calls:
                    if isinstance(call, tuple) and call[0] == "move":
                        window_x += call[1]
                chrome.calls.clear()

            assert window_x == pytest.approx(60.0)
        finally:
            layer.release()

    def test_a_still_cursor_stops_asking_the_window_to_move(self) -> None:
        """Every move is a round trip to the window manager. Holding the
        button without moving must cost nothing."""
        chrome = FakeChrome()
        bar = TitleBar("Studio", chrome)
        layer = _layer(bar)
        io = imgui.get_io()
        try:
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_pos_event(400.0, HEIGHT * 0.5)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_button_event(0, True)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            chrome.calls.clear()
            for _ in range(5):
                layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert chrome.calls == []
        finally:
            layer.release()

    def test_releasing_forgets_where_the_drag_started(self) -> None:
        """A stale grab point would make the next press jump the window by
        the distance between the two."""
        chrome = FakeChrome()
        bar = TitleBar("Studio", chrome)
        layer = _layer(bar)
        io = imgui.get_io()
        try:
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_pos_event(300.0, HEIGHT * 0.5)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_button_event(0, True)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_button_event(0, False)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            chrome.calls.clear()
            # Press again somewhere far away. The first frame of the new
            # drag must not move the window at all.
            io.add_mouse_pos_event(700.0, HEIGHT * 0.5)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_button_event(0, True)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            # The new drag reads the position afresh; what must not happen
            # is a move, which a stale grab point would have produced.
            assert [c for c in chrome.calls if c != "begin_move"] == []
        finally:
            layer.release()

    def test_pressing_a_window_button_does_not_start_a_drag(self) -> None:
        chrome = FakeChrome()
        bar = TitleBar("Studio", chrome)
        layer = _layer(bar)
        io = imgui.get_io()
        try:
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_pos_event(WIDTH - BUTTON_WIDTH * 0.5, HEIGHT * 0.5)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_button_event(0, True)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert not bar.dragging
            io.add_mouse_pos_event(WIDTH - BUTTON_WIDTH * 0.5 + 20.0, HEIGHT * 0.5)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert not any(
                isinstance(call, tuple) and call[0] == "move" for call in chrome.calls
            )
        finally:
            layer.release()

    def test_a_drag_reads_the_window_position_once(self) -> None:
        """Not once per frame. The read costs something on every frame of
        a drag and is asynchronous besides, so a position read straight
        after a move can still be the old one."""
        chrome = FakeChrome()
        bar = TitleBar("Studio", chrome)
        layer = _layer(bar)
        io = imgui.get_io()
        try:
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_pos_event(400.0, HEIGHT * 0.5)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_button_event(0, True)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert chrome.calls.count("begin_move") == 1
            for step in range(3):
                io.add_mouse_pos_event(410.0 + step * 10, HEIGHT * 0.5)
                layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert chrome.calls.count("begin_move") == 1
            assert "end_move" not in chrome.calls
            io.add_mouse_button_event(0, False)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert chrome.calls.count("end_move") == 1
        finally:
            layer.release()

    def test_pressing_the_menu_does_not_start_a_drag(self) -> None:
        chrome = FakeChrome()
        bar = TitleBar("Studio", chrome)
        layer = _layer(bar)
        io = imgui.get_io()
        try:
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_pos_event(8.0, HEIGHT * 0.5)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            io.add_mouse_button_event(0, True)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert not bar.dragging
        finally:
            layer.release()


@pytest.mark.unit
class TestRouting:
    def test_a_click_with_no_preceding_motion_still_presses(self) -> None:
        """What a drag leaves behind: the window moved out from under a
        cursor that never moved, so every window-relative coordinate
        changed and SDL emitted no motion event. The press carries its own
        position, and routing it through the layer has to keep it."""
        chrome = FakeChrome()
        bar = TitleBar("Studio", chrome)
        layer = _layer(bar)
        try:
            # Settle with the cursor somewhere else entirely.
            imgui.get_io().add_mouse_pos_event(10.0, 400.0)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)

            close_x = int(WIDTH - BUTTON_WIDTH * 0.5)
            close_y = int(HEIGHT * 0.5)
            layer.process_event(
                MouseButtonEvent(button=1, x=close_x, y=close_y, is_down=True)
            )
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            layer.process_event(
                MouseButtonEvent(button=1, x=close_x, y=close_y, is_down=False)
            )
            layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert bar.close_requested
        finally:
            layer.release()


@pytest.mark.unit
class TestDegradation:
    def test_a_refusing_backend_does_not_break_the_frame(self) -> None:
        bar = TitleBar("Studio", RefusingChrome())
        layer = _layer(bar)
        try:
            for x in (
                WIDTH - BUTTON_WIDTH * 0.5,
                WIDTH - BUTTON_WIDTH * 1.5,
                WIDTH - BUTTON_WIDTH * 2.5,
            ):
                _click_at(layer, x, HEIGHT * 0.5)
            draw_data = layer.build_frame(WIDTH, HEIGHT_PX, dt=1 / 60)
            assert draw_data.total_vtx_count > 0
            # Pressed and swallowed: the bar still knows a close was asked
            # for, even though the backend could not act on it.
            assert bar.close_requested
        finally:
            layer.release()


@pytest.mark.unit
class TestChromeProtocol:
    def test_the_stub_satisfies_the_protocol(self) -> None:
        assert isinstance(FakeChrome(), IWindowChrome)

    def test_something_without_the_controls_does_not(self) -> None:
        class Bare:
            pass

        assert not isinstance(Bare(), IWindowChrome)

    def test_the_moderngl_backend_offers_the_controls(self) -> None:
        from pyguara.graphics.backends.moderngl.window import PygameGLWindow

        for name in (
            "minimize",
            "maximize",
            "restore",
            "request_close",
            "move_by",
            "is_maximized",
        ):
            assert hasattr(PygameGLWindow, name), name
