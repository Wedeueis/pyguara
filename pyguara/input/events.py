"""Input event definitions."""

from dataclasses import dataclass
from typing import Set, Any, Tuple
from pyguara.events.protocols import Event
from pyguara.input.types import GamepadButton, GamepadAxis


@dataclass
class OnActionEvent(Event):
    """Fired when a semantic action is triggered (e.g., 'Jump')."""

    action_name: str
    context: str
    value: float = 1.0  # 1.0 for press, 0.0 for release, or analog value
    timestamp: float = 0.0
    source: Any = None


@dataclass
class OnRawKeyEvent(Event):
    """Fired when a physical key is pressed/released (low-level)."""

    key_code: int
    is_down: bool
    modifiers: Set[int]
    timestamp: float = 0.0
    source: Any = None


@dataclass
class OnMouseEvent(Event):
    """Fired on mouse activity."""

    position: Tuple[int, int]
    button: int = 0
    is_down: bool = False
    is_motion: bool = False
    timestamp: float = 0.0
    source: Any = None


@dataclass
class GamepadButtonEvent(Event):
    """Fired when a gamepad button is pressed or released."""

    controller_id: int  # Which controller (0-3)
    button: GamepadButton
    is_pressed: bool  # True for press, False for release
    timestamp: float = 0.0
    source: Any = None


@dataclass
class GamepadAxisEvent(Event):
    """Fired when a gamepad analog axis changes value."""

    controller_id: int  # Which controller (0-3)
    axis: GamepadAxis
    value: float  # -1.0 to 1.0 for sticks, 0.0 to 1.0 for triggers
    previous_value: float = 0.0
    timestamp: float = 0.0
    source: Any = None
