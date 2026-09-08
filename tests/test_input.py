from types import SimpleNamespace
from typing import Any

# We need to mock pygame constants since we mocked the module
import pygame

from pyguara.input.events import (
    GamepadAxisEvent,
    GamepadButtonEvent,
    InputContextChangedEvent,
    OnActionEvent,
)
from pyguara.input.gamepad import GamepadManager
from pyguara.input.manager import InputManager
from pyguara.input.types import (
    ActionType,
    GamepadAxis,
    GamepadButton,
    GamepadConfig,
    InputAction,
    InputContext,
    InputDevice,
)

pygame.KEYDOWN = 1
pygame.KEYUP = 2
pygame.MOUSEBUTTONDOWN = 3
pygame.MOUSEBUTTONUP = 4
pygame.K_SPACE = 32


class _StubJoystick:
    """Minimal `IJoystick` stub: button/axis state is set directly by tests
    (`joystick.button_states[i] = True`) to simulate hardware without pygame."""

    def __init__(
        self,
        instance_id: int,
        name: str,
        num_buttons: int = 17,
        num_axes: int = 6,
    ) -> None:
        self.instance_id = instance_id
        self.name = name
        self.num_buttons = num_buttons
        self.num_axes = num_axes
        self.button_states: dict[int, bool] = {}
        self.axis_values: dict[int, float] = {}
        self.rumble_calls: list[tuple[float, float, int]] = []

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

    def rumble(
        self, low_frequency: float, high_frequency: float, duration_ms: int
    ) -> bool:
        self.rumble_calls.append((low_frequency, high_frequency, duration_ms))
        return True


class _StubInputBackend:
    """Minimal `IInputBackend` stub. `joysticks` is a mutable list tests can
    append/pop between `update()` calls to simulate hot-plug/unplug."""

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


def test_input_registration(event_dispatcher: Any) -> None:
    manager = InputManager(event_dispatcher, _StubInputBackend())

    # Manually register an action
    action = InputAction(name="jump", action_type=ActionType.PRESS)
    manager._registered_actions["jump"] = action

    # Bind Space -> Jump
    manager._bindings.bind(
        InputDevice.KEYBOARD, pygame.K_SPACE, "jump", InputContext.GAMEPLAY
    )

    # Verify internal state
    actions = manager._bindings.get_actions(
        InputDevice.KEYBOARD, pygame.K_SPACE, InputContext.GAMEPLAY
    )
    assert "jump" in actions


def test_keyboard_event_processing(event_dispatcher: Any) -> None:
    manager = InputManager(event_dispatcher, _StubInputBackend())

    # Register "jump"
    action = InputAction("jump", ActionType.PRESS)
    manager._registered_actions["jump"] = action
    manager._bindings.bind(InputDevice.KEYBOARD, pygame.K_SPACE, "jump")

    # Spy on events
    events = []
    event_dispatcher.subscribe(OnActionEvent, lambda e: events.append(e))

    # Simulate KeyDown

    mock_event = SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_SPACE)

    manager.process_event(mock_event)

    assert len(events) == 1
    assert events[0].action_name == "jump"
    assert events[0].value == 1.0


def test_context_switching(event_dispatcher: Any) -> None:
    manager = InputManager(event_dispatcher, _StubInputBackend())

    # Bind same key to different actions in different contexts
    manager.register_action("jump", ActionType.PRESS)
    manager.register_action("select", ActionType.PRESS)

    manager.bind_input(
        InputDevice.KEYBOARD, pygame.K_SPACE, "jump", InputContext.GAMEPLAY
    )
    manager.bind_input(
        InputDevice.KEYBOARD, pygame.K_SPACE, "select", InputContext.MENU
    )

    events = []
    event_dispatcher.subscribe(OnActionEvent, lambda e: events.append(e.action_name))

    mock_event = SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_SPACE)

    # Default is GAMEPLAY
    assert manager.context is InputContext.GAMEPLAY
    manager.process_event(mock_event)
    assert events[-1] == "jump"

    # Switch to MENU through the public API -- not by poking a private attr.
    manager.set_context(InputContext.MENU)
    assert manager.context is InputContext.MENU
    manager.process_event(mock_event)
    assert events[-1] == "select"


def test_non_gameplay_binding_is_dead_until_context_switched(
    event_dispatcher: Any,
) -> None:
    """A binding registered for a non-active context fires nothing until the
    context is made active -- the regression that motivated exposing the API."""
    manager = InputManager(event_dispatcher, _StubInputBackend())
    manager.register_action("confirm", ActionType.PRESS)
    manager.bind_input(InputDevice.KEYBOARD, pygame.K_SPACE, "confirm", InputContext.UI)

    fired: list[str] = []
    event_dispatcher.subscribe(OnActionEvent, lambda e: fired.append(e.action_name))
    key_down = SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_SPACE)

    manager.process_event(key_down)
    assert fired == []  # GAMEPLAY is active; the UI binding is dormant

    manager.context = InputContext.UI
    manager.process_event(key_down)
    assert fired == ["confirm"]


def test_context_change_dispatches_event_once(event_dispatcher: Any) -> None:
    manager = InputManager(event_dispatcher, _StubInputBackend())
    changes: list[tuple[str, str]] = []
    event_dispatcher.subscribe(
        InputContextChangedEvent,
        lambda e: changes.append((e.old_context, e.new_context)),
    )

    manager.set_context(InputContext.MENU)
    manager.set_context(InputContext.MENU)  # no-op, no event
    manager.context = InputContext.GAMEPLAY

    assert changes == [("gameplay", "menu"), ("menu", "gameplay")]


def test_deadzone_filtering(event_dispatcher: Any) -> None:
    manager = InputManager(event_dispatcher, _StubInputBackend())

    action = InputAction("move_x", ActionType.ANALOG, deadzone=0.2)
    manager._registered_actions["move_x"] = action
    manager._bindings.bind(InputDevice.GAMEPAD, 0, "move_x")  # Axis 0

    events = []
    event_dispatcher.subscribe(OnActionEvent, lambda e: events.append(e.value))

    # Small movement (drift) -- fed directly through _handle_axis, same path
    # a GamepadButtonEvent/GamepadAxisEvent from GamepadManager would take.
    manager._handle_axis(0, 0.1)
    # Should not dispatch or dispatch 0? Logic says "if abs < deadzone: value = 0"
    # But then "if action_def.action_type == ActionType.ANALOG: _dispatch_action"
    # So it dispatches 0.0.
    assert len(events) == 1
    assert events[0] == 0.0

    # Large movement
    manager._handle_axis(0, 0.8)
    assert events[1] == 0.8


def test_dispatched_input_events_carry_a_real_timestamp(event_dispatcher: Any) -> None:
    """`OnActionEvent`/`OnRawKeyEvent` used to default `timestamp` to 0.0 and
    `InputManager` never set it, so every one read 0.0. They now stamp
    themselves at construction."""
    import time

    manager = InputManager(event_dispatcher, _StubInputBackend())
    manager.register_action("jump", ActionType.PRESS)
    manager.bind_input(InputDevice.KEYBOARD, pygame.K_SPACE, "jump")

    events: list[OnActionEvent] = []
    event_dispatcher.subscribe(OnActionEvent, events.append)

    before = time.time()
    manager.process_event(SimpleNamespace(type=pygame.KEYDOWN, key=pygame.K_SPACE))

    assert len(events) == 1
    assert before <= events[0].timestamp <= time.time()


def test_gamepad_button_event_carries_a_real_timestamp(event_dispatcher: Any) -> None:
    import time

    joystick = _StubJoystick(instance_id=0, name="Pad")
    manager = GamepadManager(event_dispatcher, _StubInputBackend([joystick]))

    events: list[GamepadButtonEvent] = []
    event_dispatcher.subscribe(GamepadButtonEvent, events.append)

    before = time.time()
    joystick.button_states[GamepadButton.A.value] = True
    manager.update()

    assert len(events) == 1
    assert before <= events[0].timestamp <= time.time()


def test_register_action_deadzone_is_stored_correctly(event_dispatcher: Any) -> None:
    """Regression: InputAction's field order used to be (name, action_type,
    cooldown, deadzone), so register_action()'s positional InputAction(name,
    action_type, deadzone) call silently stored the deadzone argument into
    the cooldown field instead. Deleting cooldown fixed this positionally."""
    manager = InputManager(event_dispatcher, _StubInputBackend())

    manager.register_action("move_x", ActionType.ANALOG, deadzone=0.35)

    assert manager._registered_actions["move_x"].deadzone == 0.35


# ========== Gamepad Tests ==========


def test_gamepad_manager_initialization(event_dispatcher: Any) -> None:
    """Test that GamepadManager initializes correctly."""
    config = GamepadConfig(deadzone=0.2, vibration_enabled=True)
    manager = GamepadManager(event_dispatcher, _StubInputBackend(), config)

    assert manager is not None
    assert manager.get_connected_controllers() is not None


def test_gamepad_detection(event_dispatcher: Any) -> None:
    """Test gamepad detection on initialization."""
    joystick = _StubJoystick(instance_id=0, name="Test Controller")
    manager = GamepadManager(event_dispatcher, _StubInputBackend([joystick]))

    # Verify controller was detected
    assert 0 in manager._controllers
    assert manager._controllers[0].name == "Test Controller"
    assert manager.is_connected(0)


def test_gamepad_button_press_event(event_dispatcher: Any) -> None:
    """Test that button press events are fired correctly."""
    joystick = _StubJoystick(instance_id=0, name="Test Controller")
    manager = GamepadManager(event_dispatcher, _StubInputBackend([joystick]))

    # Subscribe to button events
    events: list[GamepadButtonEvent] = []
    event_dispatcher.subscribe(GamepadButtonEvent, lambda e: events.append(e))

    # Simulate button press (A button = index 0)
    joystick.button_states[0] = True

    manager.update()

    # Should fire button press event
    assert len(events) == 1
    assert events[0].button == GamepadButton.A
    assert events[0].is_pressed is True
    assert events[0].controller_id == 0


def test_gamepad_axis_with_deadzone(event_dispatcher: Any) -> None:
    """Test axis values with deadzone application."""
    joystick = _StubJoystick(instance_id=0, name="Test Controller")
    config = GamepadConfig(deadzone=0.15)
    manager = GamepadManager(event_dispatcher, _StubInputBackend([joystick]), config)

    # Subscribe to axis events
    events: list[GamepadAxisEvent] = []
    event_dispatcher.subscribe(GamepadAxisEvent, lambda e: events.append(e))

    # Simulate small axis movement (within deadzone)
    joystick.axis_values[0] = 0.1

    manager.update()

    # Should not fire event (within deadzone)
    assert len(events) == 0

    # Simulate large axis movement (outside deadzone)
    joystick.axis_values[0] = 0.5

    manager.update()

    # Should fire axis event
    assert len(events) == 1
    assert events[0].axis == GamepadAxis.LEFT_STICK_X
    assert events[0].controller_id == 0
    # Value should be scaled after deadzone
    assert abs(events[0].value) > 0.0


def test_gamepad_multiple_controllers(event_dispatcher: Any) -> None:
    """Test multiple controllers can be used simultaneously."""
    joystick1 = _StubJoystick(instance_id=0, name="Controller 1")
    joystick2 = _StubJoystick(instance_id=1, name="Controller 2")
    manager = GamepadManager(
        event_dispatcher, _StubInputBackend([joystick1, joystick2])
    )

    # Verify both controllers detected
    connected = manager.get_connected_controllers()
    assert len(connected) == 2
    assert 0 in connected
    assert 1 in connected
    assert manager.get_controller_name(0) == "Controller 1"
    assert manager.get_controller_name(1) == "Controller 2"


def test_gamepad_hot_plug_detection(event_dispatcher: Any) -> None:
    """Test hot-plug/unplug handling."""
    # Start with no controllers
    backend = _StubInputBackend()
    manager = GamepadManager(event_dispatcher, backend)

    assert len(manager.get_connected_controllers()) == 0

    # Simulate controller connection
    backend.joysticks.append(_StubJoystick(instance_id=0, name="New Controller"))

    manager.update()  # Should detect new controller

    assert len(manager.get_connected_controllers()) == 1
    assert manager.is_connected(0)

    # Simulate controller disconnection
    backend.joysticks.clear()

    manager.update()  # Should detect disconnection

    assert not manager.is_connected(0)


def test_gamepad_query_methods(event_dispatcher: Any) -> None:
    """Test get_button() and get_axis() query methods."""
    joystick = _StubJoystick(instance_id=0, name="Test Controller")
    manager = GamepadManager(event_dispatcher, _StubInputBackend([joystick]))

    # Initial state
    assert not manager.get_button(0, GamepadButton.A)
    assert manager.get_axis(0, GamepadAxis.LEFT_STICK_X) == 0.0

    # Simulate button press
    joystick.button_states[0] = True
    joystick.axis_values[0] = 0.5

    manager.update()

    # Verify state updated
    assert manager.get_button(0, GamepadButton.A)
    # Axis should be non-zero after deadzone
    assert abs(manager.get_axis(0, GamepadAxis.LEFT_STICK_X)) > 0.0


def test_gamepad_rumble_support(event_dispatcher: Any) -> None:
    """Test rumble/vibration support."""
    joystick = _StubJoystick(instance_id=0, name="Test Controller")
    config = GamepadConfig(vibration_enabled=True)
    manager = GamepadManager(event_dispatcher, _StubInputBackend([joystick]), config)

    # Test rumble
    result = manager.rumble(0, low_frequency=0.5, high_frequency=0.5, duration_ms=100)

    # Should call joystick.rumble
    assert result is True
    assert joystick.rumble_calls == [(0.5, 0.5, 100)]

    # Test stop rumble
    result = manager.stop_rumble(0)
    assert result is True


def test_input_manager_gamepad_integration(event_dispatcher: Any) -> None:
    """Test that InputManager properly integrates GamepadManager."""
    config = GamepadConfig(deadzone=0.2)
    manager = InputManager(event_dispatcher, _StubInputBackend(), gamepad_config=config)

    # Verify GamepadManager is initialized
    assert manager.gamepad is not None
    assert isinstance(manager.gamepad, GamepadManager)

    # Verify update() calls gamepad update
    # (This is a basic integration test - actual behavior tested in gamepad tests)
    manager.update()  # Should not raise


def test_bound_gamepad_action_fires_from_polled_state(event_dispatcher: Any) -> None:
    """A bound GAMEPAD action fires off GamepadManager's polled state (via its
    GamepadButtonEvent/GamepadAxisEvent), not raw pygame JOY* events -- proving
    the new path (GamepadManager state -> bound Action dispatch) actually
    works, not just that GamepadManager itself updates."""
    joystick = _StubJoystick(instance_id=0, name="Test Controller")
    manager = InputManager(event_dispatcher, _StubInputBackend([joystick]))

    manager.register_action("jump", ActionType.PRESS)
    manager.bind_input(InputDevice.GAMEPAD, GamepadButton.A.value, "jump")

    events = []
    event_dispatcher.subscribe(OnActionEvent, lambda e: events.append(e))

    # No pygame event of any kind -- just polled joystick state plus
    # InputManager.update(), exactly as Application.run() drives it.
    joystick.button_states[GamepadButton.A.value] = True
    manager.update()

    assert len(events) == 1
    assert events[0].action_name == "jump"
    assert events[0].value == 1.0

    # Release should not re-fire a PRESS-type action.
    joystick.button_states[GamepadButton.A.value] = False
    manager.update()

    assert len(events) == 1
