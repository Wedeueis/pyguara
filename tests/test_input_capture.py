"""Capturing a binding from the next press, as a settings screen does."""

from __future__ import annotations

import pytest

from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.input import KeyDownEvent, KeyUpEvent, MouseButtonEvent
from pyguara.input import BindingCaptureEndedEvent, PlayerRouter
from pyguara.input.backends.null_backend import NullInputBackend
from pyguara.input.binding import KeyBindingManager
from pyguara.input.events import GamepadButtonEvent, OnActionEvent, OnRawKeyEvent
from pyguara.input.keys import ESCAPE
from pyguara.input.manager import InputManager
from pyguara.input.types import (
    ActionType,
    ConflictResolution,
    GamepadButton,
    InputContext,
    InputDevice,
    RebindResult,
)

SPACE, F, G = 32, 102, 103
GAMEPLAY = InputContext.GAMEPLAY


@pytest.fixture
def dispatcher() -> EventDispatcher:
    return EventDispatcher()


@pytest.fixture
def manager(dispatcher: EventDispatcher) -> InputManager:
    manager = InputManager(dispatcher, NullInputBackend())
    for name in ("jump", "use"):
        manager.register_action(name, ActionType.HOLD)
    manager.bind_input(InputDevice.KEYBOARD, SPACE, "jump")
    manager.bind_input(InputDevice.GAMEPAD, GamepadButton.A.value, "jump")
    manager.bind_input(InputDevice.KEYBOARD, F, "use")
    return manager


@pytest.fixture
def ended(dispatcher: EventDispatcher) -> list[BindingCaptureEndedEvent]:
    events: list[BindingCaptureEndedEvent] = []
    dispatcher.subscribe(BindingCaptureEndedEvent, events.append)
    return events


@pytest.fixture
def heard(dispatcher: EventDispatcher) -> list[object]:
    events: list[object] = []
    dispatcher.subscribe(OnActionEvent, events.append)
    dispatcher.subscribe(OnRawKeyEvent, events.append)
    return events


def _keys(manager: InputManager, action: str) -> list[tuple[InputDevice, int]]:
    return manager.bindings.get_bindings_for_action(action, GAMEPLAY)


def test_the_next_key_becomes_the_binding_on_that_device_only(
    manager: InputManager, ended: list[BindingCaptureEndedEvent]
) -> None:
    manager.capture_binding("jump")
    assert manager.capturing == "jump"
    manager.process_event(KeyDownEvent(key_code=G))

    assert manager.capturing is None
    assert sorted(_keys(manager, "jump"), key=str) == sorted(
        [(InputDevice.KEYBOARD, G), (InputDevice.GAMEPAD, GamepadButton.A.value)],
        key=str,
    )
    assert [(e.action, e.device, e.code, e.result) for e in ended] == [
        ("jump", InputDevice.KEYBOARD, G, RebindResult.SUCCESS)
    ]


def test_the_captured_press_and_its_release_reach_nothing(
    manager: InputManager, heard: list[object]
) -> None:
    manager.capture_binding("jump")
    manager.process_event(KeyDownEvent(key_code=G))
    manager.process_event(KeyUpEvent(key_code=G))
    assert heard == []
    assert not manager.is_held("jump")

    manager.process_event(KeyDownEvent(key_code=G))
    assert [e.action_name for e in heard if isinstance(e, OnActionEvent)] == ["jump"]


def test_a_key_taken_from_another_action_is_swapped_by_default(
    manager: InputManager, ended: list[BindingCaptureEndedEvent]
) -> None:
    manager.capture_binding("jump")
    manager.process_event(KeyDownEvent(key_code=F))
    assert _keys(manager, "use") == [(InputDevice.KEYBOARD, SPACE)]
    assert ended[0].result == RebindResult.SWAPPED
    assert ended[0].conflict is not None
    assert ended[0].conflict.existing_actions == ["use"]


def test_a_swap_trades_keys_on_the_same_device_only(manager: InputManager) -> None:
    manager.capture_binding("jump", devices=(InputDevice.GAMEPAD,))
    manager.bind_input(InputDevice.GAMEPAD, GamepadButton.X.value, "use")
    manager._dispatcher.dispatch(GamepadButtonEvent(0, GamepadButton.X, True))
    assert sorted(_keys(manager, "use"), key=str) == sorted(
        [(InputDevice.KEYBOARD, F), (InputDevice.GAMEPAD, GamepadButton.A.value)],
        key=str,
    )


def test_escape_cancels_and_binds_nothing(
    manager: InputManager, ended: list[BindingCaptureEndedEvent], heard: list[object]
) -> None:
    manager.capture_binding("jump")
    manager.process_event(KeyDownEvent(key_code=ESCAPE))
    manager.process_event(KeyUpEvent(key_code=ESCAPE))
    assert (InputDevice.KEYBOARD, SPACE) in _keys(manager, "jump")
    assert [(e.result, e.device, e.code) for e in ended] == [(None, None, None)]
    assert heard == [], "the cancelling press does not also close the menu"


def test_a_device_not_listened_to_passes_through(
    manager: InputManager, ended: list[BindingCaptureEndedEvent]
) -> None:
    manager.capture_binding("jump", devices=(InputDevice.GAMEPAD,))
    manager.process_event(MouseButtonEvent(button=1, x=0, y=0, is_down=True))
    manager.process_event(KeyDownEvent(key_code=G))
    assert manager.capturing == "jump"
    assert ended == []


def test_a_key_already_down_when_the_capture_starts_is_not_taken(
    manager: InputManager,
) -> None:
    manager.process_event(KeyDownEvent(key_code=SPACE))
    manager.capture_binding("use")
    manager.process_event(KeyDownEvent(key_code=SPACE))  # key repeat
    assert manager.capturing == "use"


def test_only_the_named_players_devices_are_taken(
    dispatcher: EventDispatcher, ended: list[BindingCaptureEndedEvent]
) -> None:
    router = PlayerRouter(dispatcher)
    manager = InputManager(dispatcher, NullInputBackend(), player_router=router)
    manager.register_action("jump", ActionType.PRESS)
    router.assign(InputDevice.GAMEPAD, 0, 0)
    router.assign(InputDevice.GAMEPAD, 1, 1)

    manager.capture_binding("jump", devices=(InputDevice.GAMEPAD,), player=1)
    dispatcher.dispatch(GamepadButtonEvent(0, GamepadButton.B, True))
    assert manager.capturing == "jump"
    dispatcher.dispatch(GamepadButtonEvent(1, GamepadButton.B, True))
    assert [e.code for e in ended] == [GamepadButton.B.value]


def test_a_new_capture_cancels_the_waiting_one(
    manager: InputManager, ended: list[BindingCaptureEndedEvent]
) -> None:
    manager.capture_binding("jump")
    manager.capture_binding("use")
    assert manager.capturing == "use"
    assert [(e.action, e.result) for e in ended] == [("jump", None)]
    assert manager.cancel_capture()
    assert not manager.cancel_capture()


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"action": "fly"}, "unregistered"),
        ({"action": "jump", "devices": ()}, "at least one device"),
        ({"action": "jump", "resolution": ConflictResolution.ERROR}, "SWAP"),
    ],
)
def test_bad_captures_are_refused(
    manager: InputManager, kwargs: dict[str, object], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        manager.capture_binding(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# The per-device rebind it is built on                                         #
# --------------------------------------------------------------------------- #


def test_unbind_on_one_device_keeps_the_others() -> None:
    bindings = KeyBindingManager()
    bindings.bind(InputDevice.KEYBOARD, SPACE, "jump", GAMEPLAY)
    bindings.bind(InputDevice.GAMEPAD, 0, "jump", GAMEPLAY)
    bindings.unbind("jump", GAMEPLAY, InputDevice.KEYBOARD)
    assert bindings.get_bindings_for_action("jump", GAMEPLAY) == [
        (InputDevice.GAMEPAD, 0)
    ]
    assert bindings.get_actions(InputDevice.KEYBOARD, SPACE, GAMEPLAY) == []


def test_rebind_without_device_only_still_replaces_every_device() -> None:
    bindings = KeyBindingManager()
    bindings.bind(InputDevice.KEYBOARD, SPACE, "jump", GAMEPLAY)
    bindings.bind(InputDevice.GAMEPAD, 0, "jump", GAMEPLAY)
    bindings.rebind("jump", InputDevice.KEYBOARD, G, GAMEPLAY)
    assert bindings.get_bindings_for_action("jump", GAMEPLAY) == [
        (InputDevice.KEYBOARD, G)
    ]
