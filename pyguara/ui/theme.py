"""Theme management system."""

from typing import Optional
from copy import deepcopy
from pyguara.ui.types import ColorScheme, SpacingScheme


class UITheme:
    """Central styling configuration."""

    def __init__(
        self,
        colors: Optional[ColorScheme] = None,
        spacing: Optional[SpacingScheme] = None,
    ) -> None:
        """Initialize the theme with optional overrides."""
        self.colors = colors or ColorScheme()
        self.spacing = spacing or SpacingScheme()

    def clone(self) -> "UITheme":
        """Create a deep copy of the theme."""
        return UITheme(colors=deepcopy(self.colors), spacing=deepcopy(self.spacing))


# Global default (can be swapped at runtime)
_current_theme = UITheme()


def get_theme() -> UITheme:
    """Retrieve the current active theme."""
    return _current_theme


def set_theme(theme: UITheme) -> None:
    """Set the active theme globally."""
    global _current_theme
    _current_theme = theme
