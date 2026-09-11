"""Tests for local co-op input routing (#73's P1 item): `PlayerRouter`,
`GamepadDisconnectedEvent`, and `InputManager`'s player attribution.
"""

from typing import Any

from pyguara.input.coop import PlayerRouter
from pyguara.input.events import (
    GamepadButtonEvent,
    GamepadDisconnectedEvent,
    OnActionEvent,
    PlayerJoinedEvent,
    PlayerLeftEvent,
)
from pyguara.input.manager import InputManager
from pyguara.input.types import ActionType, GamepadButton, InputDevice


class _StubJoystick:
    """Minimal `IJoystick` stub, matching `tests/test_input.py`'s."""

    def __init__(
        self, instance_id: int, name: str, num_buttons: int = 17, num_axes: int = 6
    ) -> None:
        self.instance_id = instance_id
        self.name = name
        self.num_buttons = num_buttons
        self.num_axes = num_axes
        self.button_states: dict[int, bool] = {}
        self.axis_values: dict[int, float] = {}

    def init(self) -> None:
        pass

    def quit(self) -> None:
        pass

    def get_instance_id(self) -> int:
        return self.instance_id

    def get_name(self) -> str:
        return self.name

    def get_numbuttons(self) -> int:
        return self.num_buttons

    def get_numaxes(self) -> int:
        return self.num_axes

    def get_button(self, button_index: int) -> bool:
        return self.button_states.get(button_index, False)

    def get_axis(self, axis_index: int) -> float:
        return self.axis_values.get(axis_index, 0.0)

    def rumble(self, low: float, high: float, duration_ms: int) -> bool:
        return True


class _StubInputBackend:
    def __init__(self, joysticks: list[_StubJoystick] | None = None) -> None:
        self.joysticks: list[_StubJoystick] = list(joysticks or [])
        self._initialized = False

    def init_joysticks(self) -> None:
        self._initialized = True

    def quit_joysticks(self) -> None:
        self._initialized = False

    def is_initialized(self) -> bool:
        return self._initialized

    def get_joystick_count(self) -> int:
        return len(self.joysticks)

    def get_joystick(self, device_index: int) -> _StubJoystick:
        return self.joysticks[device_index]


# ========== PlayerRouter: assignment ==========


def test_assign_sets_player_for(event_dispatcher: Any) -> None:
    router = PlayerRouter(event_dispatcher)

    router.assign(InputDevice.GAMEPAD, 0, 1)

    assert router.player_for(InputDevice.GAMEPAD, 0) == 1


def test_assign_fires_player_joined_event(event_dispatcher: Any) -> None:
    router = PlayerRouter(event_dispatcher)
    events: list[PlayerJoinedEvent] = []
    event_dispatcher.subscribe(PlayerJoinedEvent, events.append)

    router.assign(InputDevice.KEYBOARD, None, 0)

    assert len(events) == 1
    assert events[0].player == 0
    assert events[0].device == InputDevice.KEYBOARD
    assert events[0].controller_id is None


def test_unassigned_device_player_for_is_none(event_dispatcher: Any) -> None:
    router = PlayerRouter(event_dispatcher)

    assert router.player_for(InputDevice.GAMEPAD, 0) is None


# ========== PlayerRouter: dynamic join via GamepadButtonEvent ==========


def test_join_button_assigns_the_next_free_player(event_dispatcher: Any) -> None:
    router = PlayerRouter(event_dispatcher)

    event_dispatcher.dispatch(
        GamepadButtonEvent(controller_id=0, button=GamepadButton.START, is_pressed=True)
    )

    assert router.player_for(InputDevice.GAMEPAD, 0) == 0


def test_join_skips_slots_already_taken(event_dispatcher: Any) -> None:
    router = PlayerRouter(event_dispatcher)
    router.assign(InputDevice.KEYBOARD, None, 0)

    event_dispatcher.dispatch(
        GamepadButtonEvent(controller_id=0, button=GamepadButton.START, is_pressed=True)
    )

    assert router.player_for(InputDevice.GAMEPAD, 0) == 1


def test_non_join_button_press_does_not_assign(event_dispatcher: Any) -> None:
    router = PlayerRouter(event_dispatcher)

    event_dispatcher.dispatch(
        GamepadButtonEvent(controller_id=0, button=GamepadButton.A, is_pressed=True)
    )

    assert router.player_for(InputDevice.GAMEPAD, 0) is None


def test_join_button_release_does_not_assign(event_dispatcher: Any) -> None:
    router = PlayerRouter(event_dispatcher)

    event_dispatcher.dispatch(
        GamepadButtonEvent(
            controller_id=0, button=GamepadButton.START, is_pressed=False
        )
    )

    assert router.player_for(InputDevice.GAMEPAD, 0) is None


def test_join_button_on_an_already_assigned_pad_does_not_reassign(
    event_dispatcher: Any,
) -> None:
    router = PlayerRouter(event_dispatcher)
    router.assign(InputDevice.GAMEPAD, 0, 3)
    events: list[PlayerJoinedEvent] = []
    event_dispatcher.subscribe(PlayerJoinedEvent, events.append)

    event_dispatcher.dispatch(
        GamepadButtonEvent(controller_id=0, button=GamepadButton.START, is_pressed=True)
    )

    assert router.player_for(InputDevice.GAMEPAD, 0) == 3
    assert events == []  # no new join fired for an already-assigned pad


def test_two_pads_joining_claim_distinct_players(event_dispatcher: Any) -> None:
    router = PlayerRouter(event_dispatcher)

    event_dispatcher.dispatch(
        GamepadButtonEvent(controller_id=0, button=GamepadButton.START, is_pressed=True)
    )
    event_dispatcher.dispatch(
        GamepadButtonEvent(controller_id=1, button=GamepadButton.START, is_pressed=True)
    )

    assert router.player_for(InputDevice.GAMEPAD, 0) == 0
    assert router.player_for(InputDevice.GAMEPAD, 1) == 1


# ========== PlayerRouter: leave via GamepadDisconnectedEvent ==========


def test_disconnect_frees_the_slot_and_fires_player_left(event_dispatcher: Any) -> None:
    router = PlayerRouter(event_dispatcher)
    router.assign(InputDevice.GAMEPAD, 0, 1)
    events: list[PlayerLeftEvent] = []
    event_dispatcher.subscribe(PlayerLeftEvent, events.append)

    event_dispatcher.dispatch(GamepadDisconnectedEvent(controller_id=0))

    assert router.player_for(InputDevice.GAMEPAD, 0) is None
    assert len(events) == 1
    assert events[0].player == 1
    assert events[0].controller_id == 0


def test_disconnect_of_an_unassigned_controller_fires_nothing(
    event_dispatcher: Any,
) -> None:
    PlayerRouter(event_dispatcher)  # subscribes; nothing else to reference
    events: list[PlayerLeftEvent] = []
    event_dispatcher.subscribe(PlayerLeftEvent, events.append)

    event_dispatcher.dispatch(GamepadDisconnectedEvent(controller_id=5))

    assert events == []


def test_reconnecting_after_leaving_needs_to_join_again(event_dispatcher: Any) -> None:
    """A freed slot isn't remembered -- the same physical pad, unplugged and
    replugged, must press the join button again."""
    router = PlayerRouter(event_dispatcher)
    event_dispatcher.dispatch(
        GamepadButtonEvent(controller_id=0, button=GamepadButton.START, is_pressed=True)
    )
    assert router.player_for(InputDevice.GAMEPAD, 0) == 0

    event_dispatcher.dispatch(GamepadDisconnectedEvent(controller_id=0))
    assert router.player_for(InputDevice.GAMEPAD, 0) is None


# ========== PlayerRouter: action-state tracking ==========


def test_is_pressed_and_value_for_track_dispatched_actions(
    event_dispatcher: Any,
) -> None:
    router = PlayerRouter(event_dispatcher)

    event_dispatcher.dispatch(
        OnActionEvent(action_name="jump", context="gameplay", value=1.0, player=1)
    )

    assert router.is_pressed("jump", player=1) is True
    assert router.value_for("jump", player=1) == 1.0
    # A different player's state is untouched.
    assert router.is_pressed("jump", player=0) is False


def test_is_pressed_updates_on_release(event_dispatcher: Any) -> None:
    router = PlayerRouter(event_dispatcher)
    event_dispatcher.dispatch(
        OnActionEvent(action_name="jump", context="gameplay", value=1.0, player=0)
    )
    assert router.is_pressed("jump", player=0) is True

    event_dispatcher.dispatch(
        OnActionEvent(action_name="jump", context="gameplay", value=0.0, player=0)
    )

    assert router.is_pressed("jump", player=0) is False


def test_unqueried_action_defaults_to_not_pressed(event_dispatcher: Any) -> None:
    router = PlayerRouter(event_dispatcher)

    assert router.is_pressed("never_dispatched", player=0) is False
    assert router.value_for("never_dispatched", player=0) == 0.0


# ========== InputManager integration ==========


def test_without_a_router_everything_dispatches_as_player_0(
    event_dispatcher: Any,
) -> None:
    from pyguara.events.input import KeyDownEvent
    from pyguara.input import keys

    manager = InputManager(event_dispatcher, _StubInputBackend())
    manager.register_action("jump", ActionType.PRESS)
    manager.bind_input(InputDevice.KEYBOARD, keys.SPACE, "jump")

    events: list[OnActionEvent] = []
    event_dispatcher.subscribe(OnActionEvent, events.append)
    manager.process_event(KeyDownEvent(key_code=keys.SPACE))

    assert len(events) == 1
    assert events[0].player == 0


def test_keyboard_bound_to_player_via_explicit_assign(event_dispatcher: Any) -> None:
    from pyguara.events.input import KeyDownEvent
    from pyguara.input import keys

    router = PlayerRouter(event_dispatcher)
    router.assign(InputDevice.KEYBOARD, None, 0)
    manager = InputManager(event_dispatcher, _StubInputBackend(), player_router=router)
    manager.register_action("jump", ActionType.PRESS)
    manager.bind_input(InputDevice.KEYBOARD, keys.SPACE, "jump")

    events: list[OnActionEvent] = []
    event_dispatcher.subscribe(OnActionEvent, events.append)
    manager.process_event(KeyDownEvent(key_code=keys.SPACE))

    assert len(events) == 1
    assert events[0].player == 0


def test_unassigned_gamepad_input_is_dropped_when_a_router_is_present(
    event_dispatcher: Any,
) -> None:
    joystick = _StubJoystick(instance_id=0, name="Pad")
    router = PlayerRouter(event_dispatcher)
    manager = InputManager(
        event_dispatcher, _StubInputBackend([joystick]), player_router=router
    )
    manager.register_action("jump", ActionType.PRESS)
    manager.bind_input(InputDevice.GAMEPAD, GamepadButton.A.value, "jump")

    events: list[OnActionEvent] = []
    event_dispatcher.subscribe(OnActionEvent, events.append)

    # Never joined -- pressing the bound button must do nothing.
    joystick.button_states[GamepadButton.A.value] = True
    manager.update()

    assert events == []


def test_gamepad_join_then_bound_action_attributes_to_the_joined_player(
    event_dispatcher: Any,
) -> None:
    joystick = _StubJoystick(instance_id=0, name="Pad")
    router = PlayerRouter(event_dispatcher)
    router.assign(InputDevice.KEYBOARD, None, 0)  # keyboard already owns player 0
    manager = InputManager(
        event_dispatcher, _StubInputBackend([joystick]), player_router=router
    )
    manager.register_action("jump", ActionType.PRESS)
    manager.bind_input(InputDevice.GAMEPAD, GamepadButton.A.value, "jump")

    events: list[OnActionEvent] = []
    event_dispatcher.subscribe(OnActionEvent, events.append)

    # Join first.
    joystick.button_states[GamepadButton.START.value] = True
    manager.update()
    assert router.player_for(InputDevice.GAMEPAD, 0) == 1

    # Now the bound action fires, attributed to the player it joined as.
    joystick.button_states[GamepadButton.START.value] = False
    joystick.button_states[GamepadButton.A.value] = True
    manager.update()

    assert len(events) == 1
    assert events[0].action_name == "jump"
    assert events[0].player == 1


def test_two_gamepads_route_bound_actions_to_different_players(
    event_dispatcher: Any,
) -> None:
    pad_a = _StubJoystick(instance_id=0, name="Pad A")
    pad_b = _StubJoystick(instance_id=1, name="Pad B")
    router = PlayerRouter(event_dispatcher)
    manager = InputManager(
        event_dispatcher, _StubInputBackend([pad_a, pad_b]), player_router=router
    )
    manager.register_action("jump", ActionType.PRESS)
    manager.bind_input(InputDevice.GAMEPAD, GamepadButton.A.value, "jump")

    events: list[OnActionEvent] = []
    event_dispatcher.subscribe(OnActionEvent, events.append)

    pad_a.button_states[GamepadButton.START.value] = True
    pad_b.button_states[GamepadButton.START.value] = True
    manager.update()
    pad_a.button_states[GamepadButton.START.value] = False
    pad_b.button_states[GamepadButton.START.value] = False

    pad_a.button_states[GamepadButton.A.value] = True
    pad_b.button_states[GamepadButton.A.value] = True
    manager.update()

    players = {e.player for e in events}
    assert players == {0, 1}


def test_disconnect_during_play_stops_that_pads_actions_from_dispatching(
    event_dispatcher: Any,
) -> None:
    """After a joined pad disconnects and (per GamepadManager) is dropped,
    its slot is unassigned again -- a reconnect must rejoin before its
    input resumes driving anything."""
    joystick = _StubJoystick(instance_id=0, name="Pad")
    backend = _StubInputBackend([joystick])
    router = PlayerRouter(event_dispatcher)
    manager = InputManager(event_dispatcher, backend, player_router=router)
    manager.register_action("jump", ActionType.PRESS)
    manager.bind_input(InputDevice.GAMEPAD, GamepadButton.A.value, "jump")

    joystick.button_states[GamepadButton.START.value] = True
    manager.update()
    assert router.player_for(InputDevice.GAMEPAD, 0) == 0

    backend.joysticks.clear()
    manager.update()  # GamepadManager detects the unplug, fires the disconnect

    assert router.player_for(InputDevice.GAMEPAD, 0) is None
