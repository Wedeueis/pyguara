"""Input event definitions."""

import time
from dataclasses import dataclass, field
from typing import Any

from pyguara.events.protocols import Event
from pyguara.input.types import GamepadAxis, GamepadButton

# `timestamp` uses `default_factory=time.time` rather than a `0.0` default:
# the engine's other event dataclasses (`pyguara/events/*.py`) settled on this
# after the events audit found a `0.0`-plus-`__post_init__` idiom made a genuine
# timestamp of 0.0 inexpressible and left every unstamped event reading 0.0.


@dataclass
class OnActionEvent(Event):
    """Fired when a semantic action is triggered (e.g., 'Jump')."""

    action_name: str
    context: str
    value: float = 1.0  # 1.0 for press, 0.0 for release, or analog value
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class OnRawKeyEvent(Event):
    """Fired when a physical key is pressed/released (low-level)."""

    key_code: int
    is_down: bool
    modifiers: set[int]
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class OnMouseEvent(Event):
    """Fired on mouse activity."""

    position: tuple[int, int]
    button: int = 0
    is_down: bool = False
    is_motion: bool = False
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class InputContextChangedEvent(Event):
    """Fired when `InputManager`'s active input context changes.

    Lets UI, HUD and gameplay code react to a mode switch (e.g. hiding a
    reticle when the game pauses into `MENU`) without polling
    `InputManager.context` every frame.
    """

    old_context: str
    new_context: str
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class GamepadButtonEvent(Event):
    """Fired when a gamepad button is pressed or released."""

    controller_id: int  # Which controller (0-3)
    button: GamepadButton
    is_pressed: bool  # True for press, False for release
    timestamp: float = field(default_factory=time.time)
    source: Any = None


@dataclass
class GamepadAxisEvent(Event):
    """Fired when a gamepad analog axis changes value."""

    controller_id: int  # Which controller (0-3)
    axis: GamepadAxis
    value: float  # -1.0 to 1.0 for sticks, 0.0 to 1.0 for triggers
    previous_value: float = 0.0
    timestamp: float = field(default_factory=time.time)
    source: Any = None
