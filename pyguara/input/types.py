"""Input domain definitions."""

from enum import Enum, auto
from dataclasses import dataclass


class InputDevice(Enum):
    """Physical device types."""

    KEYBOARD = auto()
    MOUSE = auto()
    GAMEPAD = auto()


class InputContext(str, Enum):
    """Defines the current 'mode' of input."""

    GAMEPLAY = "gameplay"
    UI = "ui"
    MENU = "menu"
    DEBUG = "debug"


class ActionType(Enum):
    """How the action behaves."""

    PRESS = auto()
    RELEASE = auto()
    HOLD = auto()
    ANALOG = auto()  # New: For sticks/triggers (0.0 to 1.0)


@dataclass
class InputAction:
    """Definition of a semantic action."""

    name: str
    action_type: ActionType = ActionType.PRESS
    cooldown: float = 0.0
    deadzone: float = 0.1  # New: Ignore small stick drifts
