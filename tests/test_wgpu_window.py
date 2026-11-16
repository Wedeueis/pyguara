"""The wgpu window on winit: its events, its key codes, and when it opens one.

Most of this opens no window. Translation is a pure mapping, the key table is
read straight from the extension, and `open()` is driven against a stand-in
`NativeWindow` that records what it was asked for. One test opens a real
window, and skips where there is no window system to open it on.
"""

from __future__ import annotations

import signal
from typing import Any

import pytest

from pyguara import native
from pyguara.config.types import WindowConfig
from pyguara.events.input import (
    KeyDownEvent,
    KeyUpEvent,
    MouseButtonEvent,
    MouseMotionEvent,
    MouseWheelEvent,
    TextInputEvent,
)
from pyguara.events.lifecycle import QuitEvent
from pyguara.events.window import WindowResizeEvent
from pyguara.graphics.backends.wgpu import window as window_module
from pyguara.graphics.backends.wgpu.window import WgpuWindow, translate, wants_offscreen
from pyguara.input import keys

try:
    extension: Any = native.require_extension("tests")
except RuntimeError:
    extension = None
needs_extension = pytest.mark.skipif(extension is None, reason="extension not built")

SHIFT, CTRL, ALT = 0x0003, 0x00C0, 0x0300


def same(actual: object, expected: object) -> bool:
    """Compare two events by type and fields, ignoring when each was made."""

    def fields(event: object) -> tuple[type, dict[str, Any]]:
        values = {k: v for k, v in vars(event).items() if k != "timestamp"}
        return type(event), values

    return fields(actual) == fields(expected)


class TestTranslate:
    def test_keys_carry_their_code_and_modifiers(self) -> None:
        down = translate(("key_down", keys.A, SHIFT | CTRL))
        assert same(down, KeyDownEvent(key_code=keys.A, modifiers={SHIFT, CTRL}))
        up = translate(("key_up", keys.ESCAPE, 0))
        assert same(up, KeyUpEvent(key_code=keys.ESCAPE, modifiers=set()))

    def test_mouse(self) -> None:
        button = translate(("mouse_button", 1, 10, 20, True, ALT))
        assert same(
            button,
            MouseButtonEvent(button=1, x=10, y=20, is_down=True, modifiers={ALT}),
        )
        motion = translate(("mouse_motion", 5, 6, 1, -2))
        assert same(motion, MouseMotionEvent(x=5, y=6, rel_x=1, rel_y=-2))
        assert same(translate(("wheel", 0.0, -1.0)), MouseWheelEvent(x=0.0, y=-1.0))

    def test_window_and_text(self) -> None:
        assert same(translate(("quit",)), QuitEvent())
        assert same(translate(("text", "é")), TextInputEvent(text="é"))
        resize = translate(("resize", 800, 600))
        assert same(resize, WindowResizeEvent(width=800, height=600))

    def test_an_event_the_engine_has_no_class_for_is_dropped(self) -> None:
        assert translate(("focus", True)) is None


@needs_extension
class TestKeycodes:
    """The Rust table against `pyguara.input.keys`, which is SDL's numbering.

    A saved key binding is a number. If a key's code changed with the window
    library, every binding a player saved under pygame would silently point
    at another key.
    """

    # winit's name for each key `pyguara.input.keys` names by position.
    EXPECTED = {
        "ArrowUp": keys.UP, "ArrowDown": keys.DOWN,
        "ArrowLeft": keys.LEFT, "ArrowRight": keys.RIGHT,
        "Enter": keys.RETURN, "Escape": keys.ESCAPE, "Space": keys.SPACE,
        "Tab": keys.TAB, "Backspace": keys.BACKSPACE, "Delete": keys.DELETE,
        "Home": keys.HOME, "End": keys.END, "NumpadEnter": keys.KP_ENTER,
        "ShiftLeft": keys.L_SHIFT, "ShiftRight": keys.R_SHIFT,
        "ControlLeft": keys.L_CTRL, "ControlRight": keys.R_CTRL,
        "AltLeft": keys.L_ALT, "AltRight": keys.R_ALT,
        **{f"Numpad{n}": getattr(keys, f"KP_{n}") for n in range(10)},
        **{f"F{n}": getattr(keys, f"F{n}") for n in range(1, 13)},
    }  # fmt: skip

    def test_every_positional_key_the_engine_names_maps_to_its_value(self) -> None:
        table = dict(extension.keycode_table())  # type: ignore[union-attr]
        for name, code in self.EXPECTED.items():
            assert table.get(name) == code, name

    def test_no_two_keys_share_a_code(self) -> None:
        codes = [code for _, code in extension.keycode_table()]  # type: ignore[union-attr]
        assert len(codes) == len(set(codes))


class TestOffscreen:
    @pytest.mark.parametrize(
        ("variables", "expected"),
        [
            ({"PYGUARA_WINDOW": "offscreen"}, True),
            ({"PYGUARA_WINDOW": "OFFSCREEN"}, True),
            ({"PYGUARA_WINDOW": "window"}, False),
            # SDL's variable configures a library this window does not use.
            ({"SDL_VIDEODRIVER": "dummy"}, False),
            ({}, False),
        ],
    )
    def test_what_asks_for_no_window(
        self,
        monkeypatch: pytest.MonkeyPatch,
        variables: dict[str, str],
        expected: bool,
    ) -> None:
        monkeypatch.delenv("PYGUARA_WINDOW", raising=False)
        monkeypatch.delenv("SDL_VIDEODRIVER", raising=False)
        for name, value in variables.items():
            monkeypatch.setenv(name, value)
        assert wants_offscreen() is expected


class _Recorder:
    """Stands in for `NativeWindow`, recording how it was opened."""

    opened: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _Recorder.opened.append((args, kwargs))
        self.size = (args[1], args[2])
        self.pumped: list[tuple[Any, ...]] = []

    def native_handles(self) -> None:
        return None

    def pump(self) -> list[tuple[Any, ...]]:
        events, self.pumped = self.pumped, []
        return events

    def close(self) -> None: ...


class _Extension:
    NativeWindow = _Recorder


class _Gpu:
    def detach_window(self) -> None: ...


class _Frame:
    def __init__(self, *args: Any) -> None:
        self.args = args
        self.gpu: Any = _Gpu()


@pytest.fixture
def recorded(monkeypatch: pytest.MonkeyPatch) -> type[_Recorder]:
    monkeypatch.delenv("PYGUARA_WINDOW", raising=False)
    monkeypatch.setattr(native, "require_extension", lambda _why: _Extension)
    monkeypatch.setattr(window_module, "GpuFrame", _Frame)
    _Recorder.opened = []
    return _Recorder


class TestOpen:
    def test_the_config_reaches_the_window(self, recorded: type[_Recorder]) -> None:
        config = WindowConfig(
            title="t", screen_width=320, screen_height=200,
            fullscreen=True, resizable=True, borderless=True,
        )  # fmt: skip
        WgpuWindow().open(config)

        (args, kwargs) = recorded.opened[0]
        assert args == ("t", 320, 200)
        assert kwargs == {"fullscreen": True, "resizable": True, "borderless": True}

    def test_a_window_that_cannot_open_falls_back_offscreen(
        self, monkeypatch: pytest.MonkeyPatch, recorded: type[_Recorder]
    ) -> None:
        def refuse(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("no window system is available")

        monkeypatch.setattr(_Extension, "NativeWindow", refuse)
        window = WgpuWindow()

        assert window.open(WindowConfig(screen_width=64, screen_height=48))
        assert window.has_window is False
        assert window.frame.args[:3] == (64, 48, None)  # type: ignore[union-attr]
        monkeypatch.setattr(_Extension, "NativeWindow", _Recorder)

    def test_posted_events_come_before_the_windows_own(
        self, recorded: type[_Recorder]
    ) -> None:
        window = WgpuWindow()
        window.open(WindowConfig())
        window._window.pumped = [("key_down", keys.A, 0)]
        window.post_event(KeyDownEvent(key_code=keys.B))

        codes = [event.key_code for event in window.poll_events()]  # type: ignore[attr-defined]
        assert codes == [keys.B, keys.A]

    def test_a_resize_is_adopted_and_a_minimise_is_not(
        self, recorded: type[_Recorder]
    ) -> None:
        window = WgpuWindow()
        window.open(WindowConfig(screen_width=100, screen_height=100))
        window._window.pumped = [("resize", 0, 0), ("resize", 300, 200)]

        events = list(window.poll_events())

        assert len(events) == 1
        assert same(events[0], WindowResizeEvent(width=300, height=200))
        assert (window.width, window.height) == (300, 200)

    def test_a_requested_close_quits_through_the_queue(
        self, recorded: type[_Recorder]
    ) -> None:
        window = WgpuWindow()
        window.open(WindowConfig())
        window.request_close()

        (event,) = window.poll_events()
        assert isinstance(event, QuitEvent)
        assert list(window.poll_events()) == []


class TestSigterm:
    """SIGTERM must end the game, and cleanly.

    SDL used to turn it into a quit for the pygame window. Without that
    window, `pygame.mixer` opening SDL still caught it and nothing read the
    queue: a windowed game ignored SIGTERM until it was SIGKILLed.
    """

    def test_sigterm_becomes_a_quit_and_close_restores_the_handler(
        self, recorded: type[_Recorder]
    ) -> None:
        before = signal.signal(signal.SIGTERM, signal.SIG_DFL)
        try:
            window = WgpuWindow()
            window.open(WindowConfig())
            signal.raise_signal(signal.SIGTERM)

            (event,) = window.poll_events()
            assert isinstance(event, QuitEvent)
            window.close()
            assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
        finally:
            signal.signal(signal.SIGTERM, before)

    def test_a_games_own_handler_is_left_alone(self, recorded: type[_Recorder]) -> None:
        def mine(_signum: int, _frame: object) -> None: ...

        before = signal.signal(signal.SIGTERM, mine)
        try:
            window = WgpuWindow()
            window.open(WindowConfig())
            assert signal.getsignal(signal.SIGTERM) is mine
            window.close()
        finally:
            signal.signal(signal.SIGTERM, before)


@needs_extension
class TestFallingBack:
    def test_a_window_that_cannot_be_drawn_to_falls_back(self) -> None:
        from pyguara.graphics.backends.wgpu import GpuFrame

        try:
            frame = GpuFrame(16, 16, ("not-a-platform", 1, 1))
        except RuntimeError as error:
            pytest.skip(f"no graphics adapter for wgpu: {error}")

        assert frame.gpu.has_surface is False
        assert frame.gpu.present() is False
        frame.gpu.clear(9, 9, 9, 255)
        frame.gpu.end_frame()
        assert frame.gpu.read_pixels()[:4] == bytes([9, 9, 9, 255])

    def test_null_handles_are_refused_not_dereferenced(self) -> None:
        gpu = extension.NativeGpu  # type: ignore[union-attr]
        for kind, window, display in (
            ("win32", 0, 0),
            ("x11", 5, 0),
            ("wayland", 0, 5),
            ("appkit", 0, 0),
        ):
            with pytest.raises(ValueError, match="null"):
                gpu.for_window(kind, window, display, 16, 16)


@needs_extension
@pytest.mark.integration
def test_a_real_window_opens_presents_and_reopens() -> None:
    """winit allows one event loop per process; the window must not need two."""
    try:
        first = extension.NativeWindow("pyguara test", 160, 120)  # type: ignore[union-attr]
    except RuntimeError as error:
        pytest.skip(f"no window system: {error}")
    try:
        assert first.size == (160, 120)
        handles = first.native_handles()
        assert handles is not None
        first.pump()
    finally:
        first.close()
    second = extension.NativeWindow("pyguara test", 80, 60)  # type: ignore[union-attr]
    try:
        assert second.size == (80, 60)
    finally:
        second.close()
    assert list(second.pump()) == []


class TestCloseReleasesTheSurfaceFirst:
    """#405: the surface must not outlive the window it draws to.

    `NativeGpu.for_window` requires the window to stay open while the GPU
    object lives, and the renderer, the UI renderer and Studio's renderer
    all hold `frame.gpu`. Dropping the window's own reference released
    nothing, so the surface outlived its window until garbage collection
    at exit, which is where CI saw a segfault.
    """

    def test_the_gpu_lets_go_of_the_window_before_it_closes(
        self, monkeypatch: pytest.MonkeyPatch, recorded: type[_Recorder]
    ) -> None:
        order: list[str] = []
        monkeypatch.setattr(_Gpu, "detach_window", lambda self: order.append("detach"))
        monkeypatch.setattr(_Recorder, "close", lambda self: order.append("close"))
        window = WgpuWindow()
        window.open(WindowConfig(screen_width=64, screen_height=48))
        held_elsewhere = window.frame.gpu  # type: ignore[union-attr]  # as a renderer does

        window.close()

        assert order == ["detach", "close"]
        assert held_elsewhere is not None


@needs_extension
def test_detaching_an_offscreen_gpu_is_safe_to_repeat() -> None:
    try:
        gpu = extension.NativeGpu(32, 32)  # type: ignore[union-attr]
    except RuntimeError as error:
        pytest.skip(f"no graphics adapter for wgpu: {error}")
    gpu.detach_window()
    gpu.detach_window()
    assert gpu.has_surface is False


@needs_extension
def test_detaching_waits_for_an_offscreen_gpu_to_finish_its_frame() -> None:
    """Nothing is still rendering once the window has been let go of.

    A software driver renders on its own threads, and a process that
    exits while one is still running a submitted frame crashes in the
    driver. So the wait cannot depend on there being a surface.
    """
    try:
        gpu = extension.NativeGpu(1024, 1024)  # type: ignore[union-attr]
    except RuntimeError as error:
        pytest.skip(f"no graphics adapter for wgpu: {error}")
    # Enough overdraw that the frame outlasts the call that submits it.
    for index in range(4000):
        gpu.rect(float(index % 900), float(index % 700), 300.0, 300.0, 255, 0, 0, 120)
    gpu.end_frame()

    gpu.detach_window()

    assert gpu.idle


@needs_extension
@pytest.mark.integration
def test_a_detached_gpu_draws_offscreen_after_its_window_is_gone() -> None:
    try:
        window = extension.NativeWindow("pyguara test", 64, 48)  # type: ignore[union-attr]
    except RuntimeError as error:
        pytest.skip(f"no window system: {error}")
    try:
        try:
            gpu = extension.NativeGpu.for_window(*window.native_handles(), 64, 48)  # type: ignore[union-attr]
        except (RuntimeError, ValueError) as error:
            pytest.skip(f"no surface for this window: {error}")
        assert gpu.has_surface
        gpu.detach_window()
        assert gpu.has_surface is False
    finally:
        window.close()
    # The window is gone and the GPU still works, offscreen.
    gpu.clear(0, 0, 0, 255)
    pixels = gpu.read_pixels()
    assert len(pixels) == 64 * 48 * 4
