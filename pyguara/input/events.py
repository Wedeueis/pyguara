"""Input event definitions."""

from dataclasses import dataclass
from typing import Set, Any, Tuple
from pyguara.events.protocols import Event


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
