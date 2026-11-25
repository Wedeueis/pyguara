"""Input subsystem.

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
from pyguara.input.gestures import (
    ActionSequence,
    Chord,
    DoubleTap,
    Gesture,
    Hold,
    Tap,
)
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
    "ActionSequence",
    "ActionType",
    "BindingConflict",
    "BindingKey",
    "Chord",
    "ConflictResolution",
    "DoubleTap",
    "GamepadAxis",
    "GamepadAxisEvent",
    "GamepadButton",
    "GamepadButtonEvent",
    "GamepadConfig",
    "GamepadDisconnectedEvent",
    "GamepadManager",
    "GamepadState",
    "Gesture",
    "Hold",
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
    "Tap",
]
