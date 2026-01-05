"""Base Widget class for interactive components."""

from pyguara.common.types import Color
from pyguara.ui.base import UIElement
from pyguara.ui.types import UIElementState


class Widget(UIElement):
    """Base class for styled UI components.

    Adds helper methods to resolve theme colors based on state.
    """

    def get_state_color(self, base_color: Color) -> Color:
        """Calculate the final color based on the current state (Hover/Press)."""
        if self.state == UIElementState.DISABLED:
            # Simple dimming for disabled state
            return Color(
                base_color.r // 2, base_color.g // 2, base_color.b // 2, base_color.a
            )

        # In a real engine, you might blend colors here.
        # For now, we return specific theme overrides if defined,
        # or just the base color.
        return base_color
