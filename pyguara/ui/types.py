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
