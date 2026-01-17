"""
Input subsystem.

Handles hardware input (Keyboard/Mouse) and translates it into semantic Actions.
"""

from pyguara.input.binding import KeyBindingManager
from pyguara.input.events import OnActionEvent, OnMouseEvent, OnRawKeyEvent
from pyguara.input.manager import InputManager
from pyguara.input.protocols import IInputBackend, IJoystick
from pyguara.input.types import ActionType, InputAction, InputContext

__all__ = [
    "ActionType",
    "IInputBackend",
    "IJoystick",
    "InputAction",
    "InputContext",
    "InputManager",
    "KeyBindingManager",
    "OnActionEvent",
    "OnMouseEvent",
    "OnRawKeyEvent",
]
