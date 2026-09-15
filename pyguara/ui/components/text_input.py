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
        self.focusable = True
        self.text = ""
        self.placeholder = placeholder
        self.active = False
        self.max_length = 32

    def render(self, renderer: UIRenderer) -> None:
        """Render the input box and text."""
        # A field is cut into the surface; the focus ring is what says it
        # is taking keystrokes, rather than the accent colour standing in.
        colors = self.theme.colors
        border_color = colors.focus_ring if self.active else colors.edge_strong

        renderer.draw_rect(self.rect, colors.surface_inset)
        renderer.draw_rect(self.rect, border_color, width=1)

        # Text. A placeholder is faint text, not a border colour that
        # happened to be dim enough.
        display_text = self.text if self.text else self.placeholder
        color = colors.text_body if self.text else colors.text_faint

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
                colors.text_body,
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

        # Focus events from UIManager
        if event_type == UIEventType.FOCUS_GAINED:
            self.active = True
            return True

        if event_type == UIEventType.FOCUS_LOST:
            self.active = False
            return True

        # Keyboard input handling
        if self.active and event_type == UIEventType.KEY_DOWN:
            if key_code == 8:  # Backspace
                if self.text:
                    self.text = self.text[:-1]
                return True
            elif key_code == 127:  # Delete
                # Delete behaves same as backspace for simple single-cursor input
                if self.text:
                    self.text = self.text[:-1]
                return True
            elif 32 <= key_code <= 126:  # Printable ASCII range
                if len(self.text) < self.max_length:
                    self.text += chr(key_code)
                return True

        return False
