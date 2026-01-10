from unittest.mock import MagicMock, Mock, patch
from typing import Any
from pyguara.input.manager import InputManager
from pyguara.input.gamepad import GamepadManager
from pyguara.input.types import (
    InputDevice,
    InputContext,
    ActionType,
    InputAction,
    GamepadButton,
    GamepadAxis,
    GamepadConfig,
)
from pyguara.input.events import OnActionEvent, GamepadButtonEvent, GamepadAxisEvent

# We need to mock pygame constants since we mocked the module
import pygame

pygame.KEYDOWN = 1
pygame.KEYUP = 2
pygame.MOUSEBUTTONDOWN = 3
pygame.MOUSEBUTTONUP = 4
pygame.JOYBUTTONDOWN = 5
pygame.JOYAXISMOTION = 6
pygame.K_SPACE = 32


def test_input_registration(event_dispatcher: Any) -> None:
    manager = InputManager(event_dispatcher)
    # Mock Joystick init

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
    manager = InputManager(event_dispatcher)

    # Register "jump"
    action = InputAction("jump", ActionType.PRESS)
    manager._registered_actions["jump"] = action
    manager._bindings.bind(InputDevice.KEYBOARD, pygame.K_SPACE, "jump")

    # Spy on events
    events = []
    event_dispatcher.subscribe(OnActionEvent, lambda e: events.append(e))

    # Simulate KeyDown
    mock_event = MagicMock()
    mock_event.type = pygame.KEYDOWN
    mock_event.key = pygame.K_SPACE

    manager.process_event(mock_event)

    assert len(events) == 1
    assert events[0].action_name == "jump"
    assert events[0].value == 1.0


def test_context_switching(event_dispatcher: Any) -> None:
    manager = InputManager(event_dispatcher)

    # Bind same key to different actions in different contexts
    manager._registered_actions["jump"] = InputAction("jump")
    manager._registered_actions["select"] = InputAction("select")

    manager._bindings.bind(
        InputDevice.KEYBOARD, pygame.K_SPACE, "jump", InputContext.GAMEPLAY
    )
    manager._bindings.bind(
        InputDevice.KEYBOARD, pygame.K_SPACE, "select", InputContext.MENU
    )

    events = []
    event_dispatcher.subscribe(OnActionEvent, lambda e: events.append(e.action_name))

    mock_event = MagicMock()
    mock_event.type = pygame.KEYDOWN
    mock_event.key = pygame.K_SPACE

    # Default is GAMEPLAY
    manager.process_event(mock_event)
    assert events[-1] == "jump"

    # Switch to MENU
    manager._context = InputContext.MENU
    manager.process_event(mock_event)
    assert events[-1] == "select"


def test_deadzone_filtering(event_dispatcher: Any) -> None:
    manager = InputManager(event_dispatcher)

    action = InputAction("move_x", ActionType.ANALOG, deadzone=0.2)
    manager._registered_actions["move_x"] = action
    manager._bindings.bind(InputDevice.GAMEPAD, 0, "move_x")  # Axis 0

    events = []
    event_dispatcher.subscribe(OnActionEvent, lambda e: events.append(e.value))

    # Small movement (drift)
    mock_event = MagicMock()
    mock_event.type = pygame.JOYAXISMOTION
    mock_event.axis = 0
    mock_event.value = 0.1

    manager.process_event(mock_event)
    # Should not dispatch or dispatch 0? Logic says "if abs < deadzone: value = 0"
    # But then "if action_def.action_type == ActionType.ANALOG: _dispatch_action"
    # So it dispatches 0.0.
    assert len(events) == 1
    assert events[0] == 0.0

    # Large movement
    mock_event.value = 0.8
    manager.process_event(mock_event)
    assert events[1] == 0.8


# ========== Gamepad Tests ==========


def test_gamepad_manager_initialization(event_dispatcher: Any) -> None:
    """Test that GamepadManager initializes correctly."""
    config = GamepadConfig(deadzone=0.2, vibration_enabled=True)
    manager = GamepadManager(event_dispatcher, config)

    assert manager is not None
    assert manager.get_connected_controllers() is not None


@patch("pygame.joystick.get_count")
@patch("pygame.joystick.Joystick")
def test_gamepad_detection(
    mock_joystick_class: Any, mock_get_count: Any, event_dispatcher: Any
) -> None:
    """Test gamepad detection on initialization."""
    # Mock one controller
    mock_get_count.return_value = 1
    mock_joystick = Mock()
    mock_joystick.get_instance_id.return_value = 0
    mock_joystick.get_name.return_value = "Test Controller"
    mock_joystick_class.return_value = mock_joystick

    manager = GamepadManager(event_dispatcher)

    # Verify controller was detected
    assert 0 in manager._controllers
    assert manager._controllers[0].name == "Test Controller"
    assert manager.is_connected(0)


@patch("pygame.joystick.get_count")
@patch("pygame.joystick.Joystick")
def test_gamepad_button_press_event(
    mock_joystick_class: Any, mock_get_count: Any, event_dispatcher: Any
) -> None:
    """Test that button press events are fired correctly."""
    # Setup mock controller
    mock_get_count.return_value = 1
    mock_joystick = Mock()
    mock_joystick.get_instance_id.return_value = 0
    mock_joystick.get_name.return_value = "Test Controller"
    mock_joystick.get_numbuttons.return_value = 17
    mock_joystick.get_numaxes.return_value = 6
    mock_joystick.get_button.return_value = False
    mock_joystick.get_axis.return_value = 0.0
    mock_joystick_class.return_value = mock_joystick

    manager = GamepadManager(event_dispatcher)

    # Subscribe to button events
    events: list[GamepadButtonEvent] = []
    event_dispatcher.subscribe(GamepadButtonEvent, lambda e: events.append(e))

    # Simulate button press (A button)
    mock_joystick.get_button.side_effect = lambda btn: btn == 0  # A button

    manager.update()

    # Should fire button press event
    assert len(events) == 1
    assert events[0].button == GamepadButton.A
    assert events[0].is_pressed is True
    assert events[0].controller_id == 0


@patch("pygame.joystick.get_count")
@patch("pygame.joystick.Joystick")
def test_gamepad_axis_with_deadzone(
    mock_joystick_class: Any, mock_get_count: Any, event_dispatcher: Any
) -> None:
    """Test axis values with deadzone application."""
    # Setup mock controller
    mock_get_count.return_value = 1
    mock_joystick = Mock()
    mock_joystick.get_instance_id.return_value = 0
    mock_joystick.get_name.return_value = "Test Controller"
    mock_joystick.get_numbuttons.return_value = 17
    mock_joystick.get_numaxes.return_value = 6
    mock_joystick.get_button.return_value = False
    mock_joystick.get_axis.return_value = 0.0
    mock_joystick_class.return_value = mock_joystick

    config = GamepadConfig(deadzone=0.15)
    manager = GamepadManager(event_dispatcher, config)

    # Subscribe to axis events
    events: list[GamepadAxisEvent] = []
    event_dispatcher.subscribe(GamepadAxisEvent, lambda e: events.append(e))

    # Simulate small axis movement (within deadzone)
    mock_joystick.get_axis.side_effect = lambda axis: 0.1 if axis == 0 else 0.0

    manager.update()

    # Should not fire event (within deadzone)
    assert len(events) == 0

    # Simulate large axis movement (outside deadzone)
    mock_joystick.get_axis.side_effect = lambda axis: 0.5 if axis == 0 else 0.0

    manager.update()

    # Should fire axis event
    assert len(events) == 1
    assert events[0].axis == GamepadAxis.LEFT_STICK_X
    assert events[0].controller_id == 0
    # Value should be scaled after deadzone
    assert abs(events[0].value) > 0.0


@patch("pygame.joystick.get_count")
@patch("pygame.joystick.Joystick")
def test_gamepad_multiple_controllers(
    mock_joystick_class: Any, mock_get_count: Any, event_dispatcher: Any
) -> None:
    """Test multiple controllers can be used simultaneously."""
    # Mock two controllers
    mock_get_count.return_value = 2

    mock_joystick1 = Mock()
    mock_joystick1.get_instance_id.return_value = 0
    mock_joystick1.get_name.return_value = "Controller 1"
    mock_joystick1.get_numbuttons.return_value = 17
    mock_joystick1.get_numaxes.return_value = 6

    mock_joystick2 = Mock()
    mock_joystick2.get_instance_id.return_value = 1
    mock_joystick2.get_name.return_value = "Controller 2"
    mock_joystick2.get_numbuttons.return_value = 17
    mock_joystick2.get_numaxes.return_value = 6

    mock_joystick_class.side_effect = [mock_joystick1, mock_joystick2]

    manager = GamepadManager(event_dispatcher)

    # Verify both controllers detected
    connected = manager.get_connected_controllers()
    assert len(connected) == 2
    assert 0 in connected
    assert 1 in connected
    assert manager.get_controller_name(0) == "Controller 1"
    assert manager.get_controller_name(1) == "Controller 2"


@patch("pygame.joystick.get_count")
@patch("pygame.joystick.Joystick")
def test_gamepad_hot_plug_detection(
    mock_joystick_class: Any, mock_get_count: Any, event_dispatcher: Any
) -> None:
    """Test hot-plug/unplug handling."""
    # Start with no controllers
    mock_get_count.return_value = 0
    manager = GamepadManager(event_dispatcher)

    assert len(manager.get_connected_controllers()) == 0

    # Simulate controller connection
    mock_get_count.return_value = 1
    mock_joystick = Mock()
    mock_joystick.get_instance_id.return_value = 0
    mock_joystick.get_name.return_value = "New Controller"
    mock_joystick.get_numbuttons.return_value = 17
    mock_joystick.get_numaxes.return_value = 6
    mock_joystick.get_button.return_value = False
    mock_joystick.get_axis.return_value = 0.0
    mock_joystick_class.return_value = mock_joystick

    manager.update()  # Should detect new controller

    assert len(manager.get_connected_controllers()) == 1
    assert manager.is_connected(0)

    # Simulate controller disconnection
    mock_get_count.return_value = 0

    manager.update()  # Should detect disconnection

    assert not manager.is_connected(0)


@patch("pygame.joystick.get_count")
@patch("pygame.joystick.Joystick")
def test_gamepad_query_methods(
    mock_joystick_class: Any, mock_get_count: Any, event_dispatcher: Any
) -> None:
    """Test get_button() and get_axis() query methods."""
    # Setup mock controller
    mock_get_count.return_value = 1
    mock_joystick = Mock()
    mock_joystick.get_instance_id.return_value = 0
    mock_joystick.get_name.return_value = "Test Controller"
    mock_joystick.get_numbuttons.return_value = 17
    mock_joystick.get_numaxes.return_value = 6
    mock_joystick.get_button.return_value = False
    mock_joystick.get_axis.return_value = 0.0
    mock_joystick_class.return_value = mock_joystick

    manager = GamepadManager(event_dispatcher)

    # Initial state
    assert not manager.get_button(0, GamepadButton.A)
    assert manager.get_axis(0, GamepadAxis.LEFT_STICK_X) == 0.0

    # Simulate button press
    mock_joystick.get_button.side_effect = lambda btn: btn == 0  # A button
    mock_joystick.get_axis.side_effect = lambda axis: 0.5 if axis == 0 else 0.0

    manager.update()

    # Verify state updated
    assert manager.get_button(0, GamepadButton.A)
    # Axis should be non-zero after deadzone
    assert abs(manager.get_axis(0, GamepadAxis.LEFT_STICK_X)) > 0.0


@patch("pygame.joystick.get_count")
@patch("pygame.joystick.Joystick")
def test_gamepad_rumble_support(
    mock_joystick_class: Any, mock_get_count: Any, event_dispatcher: Any
) -> None:
    """Test rumble/vibration support."""
    # Setup mock controller
    mock_get_count.return_value = 1
    mock_joystick = Mock()
    mock_joystick.get_instance_id.return_value = 0
    mock_joystick.get_name.return_value = "Test Controller"
    mock_joystick.rumble = Mock(return_value=None)
    mock_joystick_class.return_value = mock_joystick

    config = GamepadConfig(vibration_enabled=True)
    manager = GamepadManager(event_dispatcher, config)

    # Test rumble
    result = manager.rumble(0, low_frequency=0.5, high_frequency=0.5, duration_ms=100)

    # Should call joystick.rumble
    assert result is True
    mock_joystick.rumble.assert_called_once_with(0.5, 0.5, 100)

    # Test stop rumble
    result = manager.stop_rumble(0)
    assert result is True


def test_input_manager_gamepad_integration(event_dispatcher: Any) -> None:
    """Test that InputManager properly integrates GamepadManager."""
    config = GamepadConfig(deadzone=0.2)
    manager = InputManager(event_dispatcher, gamepad_config=config)

    # Verify GamepadManager is initialized
    assert manager.gamepad is not None
    assert isinstance(manager.gamepad, GamepadManager)

    # Verify update() calls gamepad update
    # (This is a basic integration test - actual behavior tested in gamepad tests)
    manager.update()  # Should not raise
