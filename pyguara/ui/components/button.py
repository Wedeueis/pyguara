"""Interactive button component."""

from pyguara.common.types import Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget
from pyguara.ui.types import UIElementState


class Button(Widget):
    """Clickable button with state styling."""

    def __init__(
        self, text: str, position: Vector2, size: Vector2 = Vector2(120, 40)
    ) -> None:
        """Initialize the button."""
        super().__init__(position, size)
        self.text = text
        self.padding = 5

    def render(self, renderer: UIRenderer) -> None:
        """Render the button in its current state."""
        # 1. Determine Background Color based on State
        bg_color = self.theme.colors.primary

        if self.state == UIElementState.HOVERED:
            bg_color = self.theme.colors.secondary
        elif self.state == UIElementState.PRESSED:
            bg_color = self.theme.colors.secondary
        elif self.state == UIElementState.DISABLED:
            bg_color = self.theme.colors.background

        # 2. Draw Background
        renderer.draw_rect(self.rect, bg_color, width=0)

        # 3. Draw Border
        border_color = self.theme.colors.border
        if self.state == UIElementState.FOCUSED:
            border_color = self.theme.colors.secondary
        renderer.draw_rect(self.rect, border_color, width=2)

        # 4. Draw Text (Centered)
        w, h = renderer.get_text_size(self.text, 16)

        text_x = self.rect.x + (self.rect.width - w) // 2
        text_y = self.rect.y + (self.rect.height - h) // 2

        text_color = self.theme.colors.text
        renderer.draw_text(self.text, Vector2(text_x, text_y), text_color)
