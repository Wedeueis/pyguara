"""Boolean toggle component."""

from pyguara.common.types import Vector2, Rect, Color
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget
from pyguara.ui.types import UIElementState, UIEventType


class Checkbox(Widget):
    """Clickable toggle box."""

    def __init__(self, label: str, position: Vector2, checked: bool = False) -> None:
        """Initialize the checkbox."""
        super().__init__(position, Vector2(20, 20))  # Fixed box size
        self.label = label
        self.checked = checked
        self.box_size = 20
        self.padding = 5

    def render(self, renderer: UIRenderer) -> None:
        """Render the checkbox and label."""
        # 1. Draw Box
        box_rect = Rect(self.rect.x, self.rect.y, self.box_size, self.box_size)
        bg_color = self.theme.colors.background

        if self.state == UIElementState.HOVERED:
            bg_color = Color(bg_color.r + 20, bg_color.g + 20, bg_color.b + 20, 255)

        renderer.draw_rect(box_rect, bg_color)
        renderer.draw_rect(box_rect, self.theme.colors.border, width=1)

        # 2. Draw Check (Inner Box)
        if self.checked:
            inner_size = 10
            offset = (self.box_size - inner_size) // 2
            check_rect = Rect(
                self.rect.x + offset, self.rect.y + offset, inner_size, inner_size
            )
            renderer.draw_rect(check_rect, self.theme.colors.secondary)

        # 3. Draw Label text
        text_pos = Vector2(self.rect.x + self.box_size + self.padding, self.rect.y)
        renderer.draw_text(self.label, text_pos, self.theme.colors.text)

        # Update total bounds for hit testing (Box + Text)
        text_w, _ = renderer.get_text_size(self.label, 16)
        self.rect.width = self.box_size + self.padding + text_w

    def _process_input(
        self, event_type: UIEventType, position: Vector2, button: int
    ) -> bool:
        # Standard input processing + toggle logic
        consumed = super()._process_input(event_type, position, button)
        if (
            event_type == UIEventType.MOUSE_UP
            and self.state == UIElementState.HOVERED
            and consumed
        ):
            self.checked = not self.checked
        return consumed
