"""UI domain definitions and constants."""

from enum import Enum, auto
from dataclasses import dataclass, field
from pyguara.common.types import Color  # FIX: Import Color

# --- Enums ---


class UIElementState(Enum):
    """Visual state of a UI component."""

    NORMAL = auto()
    HOVERED = auto()
    PRESSED = auto()
    DISABLED = auto()
    FOCUSED = auto()


class UIAnchor(Enum):
    """Positioning anchor point."""

    TOP_LEFT = auto()
    TOP_CENTER = auto()
    TOP_RIGHT = auto()
    CENTER_LEFT = auto()
    CENTER = auto()
    CENTER_RIGHT = auto()
    BOTTOM_LEFT = auto()
    BOTTOM_CENTER = auto()
    BOTTOM_RIGHT = auto()


class LayoutDirection(Enum):
    """Direction for container stacking."""

    HORIZONTAL = auto()
    VERTICAL = auto()


class LayoutAlignment(Enum):
    """Child alignment within containers."""

    START = auto()
    CENTER = auto()
    END = auto()
    STRETCH = auto()


class UIEventType(Enum):
    """UI interaction event types.

    Type-safe enumeration for UI events to prevent typos and enable
    IDE autocomplete. Each event represents a specific user interaction
    with UI elements.

    Example:
        >>> # Type-safe event handling
        >>> if event_type == UIEventType.MOUSE_DOWN:
        ...     element.handle_click()
        >>>
        >>> # IDE provides autocomplete
        >>> element.handle_event(UIEventType.MOUSE_MOVE, position)
    """

    MOUSE_DOWN = "mouse_down"
    """Mouse button pressed within element bounds."""

    MOUSE_UP = "mouse_up"
    """Mouse button released (may be outside element)."""

    MOUSE_MOVE = "mouse_move"
    """Mouse cursor moved (used for hover detection)."""

    MOUSE_ENTER = "mouse_enter"
    """Mouse cursor entered element bounds."""

    MOUSE_LEAVE = "mouse_leave"
    """Mouse cursor left element bounds."""

    FOCUS_GAINED = "focus_gained"
    """Element received input focus (keyboard/gamepad)."""

    FOCUS_LOST = "focus_lost"
    """Element lost input focus."""


# --- Theme Structures ---


@dataclass
class ColorScheme:
    """Standardized color palette using Color objects."""

    # FIX: Use Color objects instead of Tuples
    primary: Color = field(default_factory=lambda: Color(70, 130, 180))
    secondary: Color = field(default_factory=lambda: Color(100, 149, 237))
    background: Color = field(default_factory=lambda: Color(32, 32, 32))
    text: Color = field(default_factory=lambda: Color(255, 255, 255))
    border: Color = field(default_factory=lambda: Color(96, 96, 96))

    # State overlays
    hover_overlay: Color = field(default_factory=lambda: Color(255, 255, 255))
    press_overlay: Color = field(default_factory=lambda: Color(0, 0, 0))


@dataclass
class SpacingScheme:
    """Standardized layout spacing."""

    padding: int = 8
    margin: int = 4
    gap: int = 8
