"""Gamepads on the wgpu backend: `NativeInputBackend` over `NativeGamepads`.

No pad is plugged into a test machine, so the backend is driven against a
stand-in with the extension's interface; the extension itself is checked
for the numbering the engine depends on.
"""

from __future__ import annotations

from typing import Any

import pytest

from pyguara import native
from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.backends.native_backend import NativeInputBackend, NativeJoystick
from pyguara.input.gamepad import GamepadManager
from pyguara.input.protocols import IInputBackend, IJoystick
from pyguara.input.types import GamepadAxis, GamepadButton

try:
    extension: Any = native.require_extension("tests")
except RuntimeError:
    extension = None


class _Pads:
    """`NativeGamepads`' interface, with pads a test can plug in and press."""

    BUTTONS = 17
    AXES = 6
    error = None

    def __init__(self) -> None:
        self.connected: dict[int, str] = {}
        self.held: set[tuple[int, int]] = set()
        self.axes: dict[tuple[int, int], float] = {}
        self.polls = 0
        self.rumbled: list[tuple[int, float, float, int]] = []

    def poll(self) -> None:
        self.polls += 1

    def ids(self) -> list[int]:
        return list(self.connected)

    def name(self, pad: int) -> str | None:
        return self.connected.get(pad)

    def button(self, pad: int, index: int) -> bool:
        return (pad, index) in self.held

    def axis(self, pad: int, index: int) -> float:
        return self.axes.get((pad, index), 0.0)

    def rumble(self, pad: int, low: float, high: float, ms: int) -> bool:
        self.rumbled.append((pad, low, high, ms))
        return True


@pytest.fixture
def pads(monkeypatch: pytest.MonkeyPatch) -> _Pads:
    fake = _Pads()

    class Extension:
        @staticmethod
        def NativeGamepads() -> _Pads:  # noqa: N802 - the extension's name
            return fake

    monkeypatch.setattr(native, "require_extension", lambda _why: Extension)
    return fake


def test_the_backend_and_joystick_meet_their_protocols(pads: _Pads) -> None:
    backend = NativeInputBackend()
    backend.init_joysticks()
    pads.connected[7] = "Pad"

    assert isinstance(backend, IInputBackend)
    assert isinstance(backend.get_joystick(0), IJoystick)


def test_counting_takes_in_the_frames_events(pads: _Pads) -> None:
    backend = NativeInputBackend()
    assert backend.get_joystick_count() == 0  # not initialised: nothing read
    backend.init_joysticks()
    pads.connected.update({3: "One", 9: "Two"})

    assert backend.get_joystick_count() == 2
    assert pads.polls == 1
    assert backend.get_joystick(1).get_instance_id() == 9


def test_a_press_reaches_the_gamepad_manager(pads: _Pads) -> None:
    backend = NativeInputBackend()
    manager = GamepadManager(EventDispatcher(), backend)
    pads.connected[4] = "Xbox pad"
    manager.update()
    pads.held.add((4, GamepadButton.A.value))
    pads.axes[(4, GamepadAxis.LEFT_STICK_X.value)] = 0.9
    manager.update()

    assert manager.get_button(0, GamepadButton.A)
    assert manager.get_axis(0, GamepadAxis.LEFT_STICK_X) > 0.5


def test_unplugging_disconnects_and_a_rumble_reaches_the_pad(pads: _Pads) -> None:
    backend = NativeInputBackend()
    backend.init_joysticks()
    pads.connected[2] = "Pad"
    joystick = backend.get_joystick(0)

    assert joystick.rumble(0.5, 1.0, 200)
    assert pads.rumbled == [(2, 0.5, 1.0, 200)]
    del pads.connected[2]
    assert backend.get_joystick_count() == 0
    assert joystick.get_name() == "disconnected gamepad"


@pytest.mark.skipif(extension is None, reason="extension not built")
class TestTheExtension:
    def test_it_numbers_buttons_and_axes_as_the_engine_does(self) -> None:
        assert len(GamepadButton) == extension.NativeGamepads.BUTTONS
        assert len(GamepadAxis) == extension.NativeGamepads.AXES

    def test_a_missing_pad_reads_as_released_and_centred(self) -> None:
        pads = extension.NativeGamepads()
        pads.poll()
        assert pads.button(10_000, 0) is False
        assert pads.axis(10_000, 0) == 0.0
        assert pads.name(10_000) is None
        assert pads.rumble(10_000, 1.0, 1.0, 10) is False


def test_the_joystick_wrapper_has_no_state_of_its_own() -> None:
    pads = _Pads()
    pads.connected[1] = "Pad"
    joystick = NativeJoystick(pads, 1)
    assert (joystick.get_numbuttons(), joystick.get_numaxes()) == (17, 6)
