"""Keyboard input component."""

from pyguara.common.types import Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget
from pyguara.ui.types import UIEventType


class TextInput(Widget):
    """Editable text field."""

    def __init__(
        self, position: Vector2, width: int = 200, placeholder: str = ""
    ) -> None:
        """Initialize the text input."""
        super().__init__(position, Vector2(width, 30))
        self.text = ""
        self.placeholder = placeholder
        self.active = False
        self.max_length = 32

    def render(self, renderer: UIRenderer) -> None:
        """Render the input box and text."""
        # Background
        bg_color = self.theme.colors.background
        border_color = self.theme.colors.border

        if self.active:
            border_color = self.theme.colors.secondary

        renderer.draw_rect(self.rect, bg_color)
        renderer.draw_rect(self.rect, border_color, width=1)

        # Text
        display_text = self.text if self.text else self.placeholder
        color = self.theme.colors.text

        if not self.text:
            color = self.theme.colors.border  # Dim placeholder

        # Draw text with padding
        renderer.draw_text(
            display_text, Vector2(self.rect.x + 5, self.rect.y + 5), color
        )

        # Cursor (Blink logic would go here in update)
        if self.active:
            txt_w, _ = renderer.get_text_size(self.text, 16)
            cursor_x = self.rect.x + 5 + txt_w
            renderer.draw_line(
                Vector2(cursor_x, self.rect.y + 5),
                Vector2(cursor_x, self.rect.y + 25),
                self.theme.colors.text,
            )

    def handle_event(
        self, event_type: UIEventType, position: Vector2, key_code: int = 0
    ) -> bool:
        """Handle mouse clicks for focus and key presses for input."""
        # Mouse logic for focus
        if event_type == UIEventType.MOUSE_DOWN:
            contains = (
                self.rect.x <= position.x <= self.rect.x + self.rect.width
                and self.rect.y <= position.y <= self.rect.y + self.rect.height
            )
            self.active = contains
            if contains:
                return True

        # Keyboard logic (KEY_DOWN would need to be added to UIEventType enum)
        # For now, we only handle mouse events
        # if self.active and event_type == UIEventType.KEY_DOWN:
        #     if key_code == 8:  # Backspace
        #         self.text = self.text[:-1]
        #     return True

        return False
