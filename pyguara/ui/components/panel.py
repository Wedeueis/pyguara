"""Container background component."""

from typing import Optional
from pyguara.common.types import Vector2, Color
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget


class Panel(Widget):
    """A colored rectangle container."""

    def __init__(
        self,
        position: Vector2,
        size: Vector2,
        color: Optional[Color] = None,
        border_width: int = 1,
    ) -> None:
        """Initialize the panel."""
        super().__init__(position, size)
        self._color = color
        self.border_width = border_width

    def render(self, renderer: UIRenderer) -> None:
        """Render the panel background and border."""
        # Background
        bg_color = self._color or self.theme.colors.background
        renderer.draw_rect(self.rect, bg_color, width=0)

        # Border
        renderer.draw_rect(self.rect, self.theme.colors.border, width=self.border_width)
