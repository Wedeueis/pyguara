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

pytest.importorskip("imgui_bundle")

from imgui_bundle import imgui  # noqa: E402

from pyguara.editor.layer import EditorLayer  # noqa: E402
from pyguara.editor.titlebar import BUTTON_WIDTH, HEIGHT, TitleBar  # noqa: E402
from pyguara.graphics.protocols import IWindowChrome  # noqa: E402

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

    def move_by(self, dx: int, dy: int) -> None:
        self.calls.append(("move", dx, dy))


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

    def move_by(self, dx: int, dy: int) -> None:
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

    def test_the_layer_lends_the_bar_its_panel_menu(self) -> None:
        bar = TitleBar("Studio", FakeChrome())
        layer = _layer(bar)
        try:
            assert bar.menu == layer.draw_panel_menu_items
        finally:
            layer.release()

    def test_a_menu_passed_in_is_left_alone(self) -> None:
        def mine() -> None:  # pragma: no cover - never drawn here
            pass

        bar = TitleBar("Studio", FakeChrome(), menu=mine)
        layer = _layer(bar)
        try:
            assert bar.menu is mine
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
