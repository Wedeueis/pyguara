"""Text display components."""

from typing import Optional
from pyguara.common.types import Vector2, Color
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget
from pyguara.ui.types import UIAnchor


class Label(Widget):
    """Displays read-only text."""

    def __init__(
        self,
        text: str,
        position: Vector2 = Vector2(0, 0),
        font_size: int = 16,
        color: Optional[Color] = None,
        anchor: UIAnchor = UIAnchor.TOP_LEFT,
    ) -> None:
        """Initialize the label."""
        super().__init__(position, Vector2(0, 0), anchor=anchor)
        self.text = text
        self.font_size = font_size
        self._custom_color = color
        self._auto_size = True

    def measure(self, renderer: UIRenderer) -> None:
        """Recompute size to match text content, if auto-sizing is enabled."""
        if self._auto_size:
            w, h = renderer.get_text_size(self.text, self.font_size)
            self.rect.width = w
            self.rect.height = h

    def render(self, renderer: UIRenderer) -> None:
        """Render the text."""
        self.measure(renderer)

        final_color = self._custom_color or self.theme.colors.text
        renderer.draw_text(
            self.text, Vector2(self.rect.x, self.rect.y), final_color, self.font_size
        )

    def set_text(self, text: str) -> None:
        """Update text and force layout recalculation."""
        self.text = text
