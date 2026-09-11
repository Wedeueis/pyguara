"""
Input subsystem.

Handles hardware input (keyboard, mouse, gamepad) and translates it into
semantic Actions, with runtime rebinding and per-context bindings.
"""

from pyguara.input.binding import BindingKey, KeyBindingManager
from pyguara.input.coop import PlayerRouter
from pyguara.input.events import (
    GamepadAxisEvent,
    GamepadButtonEvent,
    GamepadDisconnectedEvent,
    InputContextChangedEvent,
    OnActionEvent,
    OnMouseEvent,
    OnRawKeyEvent,
    PlayerJoinedEvent,
    PlayerLeftEvent,
)
from pyguara.input.gamepad import GamepadManager
from pyguara.input.manager import InputManager
from pyguara.input.protocols import IInputBackend, IJoystick
from pyguara.input.types import (
    ActionType,
    BindingConflict,
    ConflictResolution,
    GamepadAxis,
    GamepadButton,
    GamepadConfig,
    GamepadState,
    InputAction,
    InputContext,
    InputDevice,
    RebindResult,
)

__all__ = [
    "ActionType",
    "BindingConflict",
    "BindingKey",
    "ConflictResolution",
    "GamepadAxis",
    "GamepadAxisEvent",
    "GamepadButton",
    "GamepadButtonEvent",
    "GamepadConfig",
    "GamepadDisconnectedEvent",
    "GamepadManager",
    "GamepadState",
    "IInputBackend",
    "IJoystick",
    "InputAction",
    "InputContext",
    "InputContextChangedEvent",
    "InputDevice",
    "InputManager",
    "KeyBindingManager",
    "OnActionEvent",
    "OnMouseEvent",
    "OnRawKeyEvent",
    "PlayerJoinedEvent",
    "PlayerLeftEvent",
    "PlayerRouter",
    "RebindResult",
]
