"""
Input subsystem.

Handles hardware input (Keyboard/Mouse) and translates it into semantic Actions.
"""

from pyguara.input.binding import BindingKey, KeyBindingManager
from pyguara.input.events import OnActionEvent, OnMouseEvent, OnRawKeyEvent
from pyguara.input.manager import InputManager
from pyguara.input.protocols import IInputBackend, IJoystick
from pyguara.input.types import (
    ActionType,
    BindingConflict,
    ConflictResolution,
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
    "IInputBackend",
    "IJoystick",
    "InputAction",
    "InputContext",
    "InputDevice",
    "InputManager",
    "KeyBindingManager",
    "OnActionEvent",
    "OnMouseEvent",
    "OnRawKeyEvent",
    "RebindResult",
]
