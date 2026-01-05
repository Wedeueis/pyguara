"""Text label component."""

from typing import Optional
from pyguara.common.types import Vector2, Color
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget


class Label(Widget):
    """Read-only text display."""

    def __init__(
        self,
        text: str,
        position: Vector2 = Vector2(0, 0),
        font_size: int = 16,
        color: Optional[Color] = None,
    ) -> None:
        """Initialize the label."""
        super().__init__(position, Vector2(0, 0))  # Size auto-calculated
        self.text = text
        self.font_size = font_size
        self._custom_color = color

    def render(self, renderer: UIRenderer) -> None:
        """Render the label text."""
        # Update size for layout engine
        w, h = renderer.get_text_size(self.text, self.font_size)
        self.rect.width = w
        self.rect.height = h

        color = self._custom_color or self.theme.colors.text
        renderer.draw_text(
            self.text, Vector2(self.rect.x, self.rect.y), color, self.font_size
        )
