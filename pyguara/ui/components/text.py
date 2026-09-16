"""Text display components."""

from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget
from pyguara.ui.types import TextAlign


class Label(Widget):
    """Displays read-only text."""

    def __init__(
        self,
        text: str,
        position: Vector2 = Vector2(0, 0),
        font_size: int = 16,
        color: Color | None = None,
        *,
        width: float | None = None,
        align: TextAlign = TextAlign.LEFT,
    ) -> None:
        """Initialize the label.

        Args:
            text: The text to display.
            position: Top-left corner.
            font_size: Font size in pixels.
            color: Text colour, or None for the theme's body text.
            width: A fixed width to lay the text out inside, or None to
                auto-size the label's rect to the text -- which is what
                every existing caller gets, unchanged. Without a fixed
                width there is nowhere for `align` to move the text: an
                auto-sized rect is exactly as wide as the text already is.
            align: Where the text sits inside `width`. A caller centring a
                label "GUARÁ & FALCÃO" against a 520px-wide panel used to
                guess the text's width by eye and hardcode an x offset --
                off by a few pixels, and wrong again the moment the text,
                the font or the panel changed. `width` + `CENTER` measures
                it instead.
        """
        super().__init__(position, Vector2(width if width is not None else 0, 0))
        self.text = text
        self.font_size = font_size
        self._custom_color = color
        self.align = align
        self._auto_size = width is None

    def measure(self, renderer: UIRenderer) -> None:
        """Recompute size to match text content, if auto-sizing is enabled.

        A fixed-width label still measures its height from the text --
        only the width is held fixed, since that is what `align` needs to
        stay stable.
        """
        w, h = renderer.get_text_size(self.text, self.font_size)
        if self._auto_size:
            self.rect.width = w
        self.rect.height = h

    def render(self, renderer: UIRenderer) -> None:
        """Render the text, positioned by `align` within the label's rect."""
        self.measure(renderer)

        final_color = self._custom_color or self.theme.colors.text
        text_width, _ = renderer.get_text_size(self.text, self.font_size)

        if self.align == TextAlign.CENTER:
            x = self.rect.x + (self.rect.width - text_width) // 2
        elif self.align == TextAlign.RIGHT:
            x = self.rect.x + self.rect.width - text_width
        else:
            x = self.rect.x

        renderer.draw_text(
            self.text, Vector2(x, self.rect.y), final_color, self.font_size
        )

    def set_text(self, text: str) -> None:
        """Update the text and force a layout recalculation.

        The recalculation is the point: a label sizes itself from its
        content, so a HUD counter going from "9" to "10" is a different
        width, and every sibling in its container moves. This said it
        forced a layout long before it did.

        Args:
            text: The new text.
        """
        if text == self.text:
            return
        self.text = text
        self.invalidate_layout()
