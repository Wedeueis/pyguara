"""Input domain definitions."""

from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Dict


class InputDevice(Enum):
    """Physical device types."""

    KEYBOARD = auto()
    MOUSE = auto()
    GAMEPAD = auto()


class GamepadButton(Enum):
    """Standard gamepad button mappings (Xbox/PlayStation layout)."""

    # Face buttons (right side)
    A = 0  # Xbox A / PlayStation Cross
    B = 1  # Xbox B / PlayStation Circle
    X = 2  # Xbox X / PlayStation Square
    Y = 3  # Xbox Y / PlayStation Triangle

    # Shoulder buttons
    LEFT_BUMPER = 4  # L1
    RIGHT_BUMPER = 5  # R1
    LEFT_TRIGGER_BUTTON = 6  # L2 (digital)
    RIGHT_TRIGGER_BUTTON = 7  # R2 (digital)

    # Center buttons
    BACK = 8  # Select / Share
    START = 9  # Start / Options
    GUIDE = 10  # Xbox / PlayStation button

    # Stick clicks
    LEFT_STICK = 11  # L3
    RIGHT_STICK = 12  # R3

    # D-Pad (some controllers report as buttons, some as hat)
    DPAD_UP = 13
    DPAD_DOWN = 14
    DPAD_LEFT = 15
    DPAD_RIGHT = 16


class GamepadAxis(Enum):
    """Standard gamepad analog axis mappings."""

    # Left analog stick
    LEFT_STICK_X = 0  # -1.0 (left) to 1.0 (right)
    LEFT_STICK_Y = 1  # -1.0 (up) to 1.0 (down)

    # Right analog stick
    RIGHT_STICK_X = 2  # -1.0 (left) to 1.0 (right)
    RIGHT_STICK_Y = 3  # -1.0 (up) to 1.0 (down)

    # Analog triggers (if not digital)
    LEFT_TRIGGER = 4  # 0.0 (not pressed) to 1.0 (fully pressed)
    RIGHT_TRIGGER = 5  # 0.0 (not pressed) to 1.0 (fully pressed)


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


@dataclass
class GamepadConfig:
    """Configuration for gamepad behavior."""

    deadzone: float = 0.15  # Ignore analog values below this threshold
    trigger_deadzone: float = 0.05  # Separate deadzone for triggers
    vibration_enabled: bool = True
    axis_sensitivity: float = 1.0  # Multiplier for axis values


@dataclass
class GamepadState:
    """Current state of a gamepad controller."""

    controller_id: int  # Unique identifier for this controller
    instance_id: int  # pygame joystick instance ID
    name: str  # Controller name (e.g., "Xbox Controller")
    is_connected: bool = True
    button_states: Dict[GamepadButton, bool] = field(
        default_factory=lambda: {button: False for button in GamepadButton}
    )
    axis_values: Dict[GamepadAxis, float] = field(
        default_factory=lambda: {axis: 0.0 for axis in GamepadAxis}
    )
