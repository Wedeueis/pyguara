from unittest.mock import MagicMock
from pyguara.input.manager import InputManager
from pyguara.input.types import InputDevice, InputContext, ActionType, InputAction
from pyguara.input.events import OnActionEvent

# We need to mock pygame constants since we mocked the module
import pygame

pygame.KEYDOWN = 1
pygame.KEYUP = 2
pygame.MOUSEBUTTONDOWN = 3
pygame.MOUSEBUTTONUP = 4
pygame.JOYBUTTONDOWN = 5
pygame.JOYAXISMOTION = 6
pygame.K_SPACE = 32


def test_input_registration(event_dispatcher):
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


def test_keyboard_event_processing(event_dispatcher):
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


def test_context_switching(event_dispatcher):
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


def test_deadzone_filtering(event_dispatcher):
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
