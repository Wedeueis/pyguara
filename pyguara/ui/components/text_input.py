"""Keyboard input component."""

from collections.abc import Callable

from pyguara.common.types import Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.input import keys
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

        # Fired on every accepted edit, so a field can drive something live
        # rather than being read once on submit.
        self.on_change: Callable[[str], None] | None = None

    def insert_text(self, text: str) -> bool:
        """Append composed text, respecting `max_length`.

        This is the path real typing takes. It receives the characters the
        platform produced -- after layout, modifiers and IME composition --
        rather than a key code this widget has to guess a character from.

        Args:
            text: The composed text, usually one character.

        Returns:
            True if anything was inserted, so a caller can tell whether the
            event was consumed.
        """
        if not self.active or not text:
            return False
        room = self.max_length - len(self.text)
        if room <= 0:
            return False
        self.set_text(self.text + text[:room])
        return True

    def set_text(self, text: str) -> None:
        """Replace the contents, firing `on_change` if they differ.

        Args:
            text: The new contents, truncated to `max_length`.
        """
        trimmed = text[: self.max_length]
        if trimmed == self.text:
            return
        self.text = trimmed
        self.invalidate_layout()
        if self.on_change is not None:
            self.on_change(trimmed)

    def render(self, renderer: UIRenderer) -> None:
        """Render the input box and text."""
        # A field is cut into the surface; the focus ring is what says it
        # is taking keystrokes, rather than the accent colour standing in.
        colors = self.theme.colors
        border_color = colors.focus_ring if self.active else colors.edge_strong

        radius = self.theme.borders.radius
        renderer.draw_rect(self.rect, colors.surface_inset, border_radius=radius)
        renderer.draw_rect(self.rect, border_color, width=1, border_radius=radius)

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

        # Editing keys only. Characters arrive through `insert_text()`,
        # driven by `TextInputEvent`.
        #
        # This used to synthesise characters here with `chr(key_code)`,
        # which cannot work: a key code is a *physical* key, so SDL reports
        # `SDLK_a` whether or not shift is held. Typing a capital letter was
        # impossible -- shift-A produced "a" -- and every non-US layout
        # produced the wrong letter, with accented and IME input out of
        # reach entirely.
        if self.active and event_type == UIEventType.KEY_DOWN:
            if key_code in (keys.BACKSPACE, keys.DELETE):
                # Delete behaves as backspace for a single-cursor field.
                if self.text:
                    self.set_text(self.text[:-1])
                return True

        return False
