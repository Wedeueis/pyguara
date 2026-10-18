"""Text display components."""

from typing import Any

from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget
from pyguara.ui.text_layout import wrap_text
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
                auto-size the label's rect to the text. Text wider than
                this **wraps**; it used to overflow, since the label made
                exactly one `draw_text` call however long the string was
                -- 423 px of text drawn through a 150 px label. Without a
                fixed width there is nothing to wrap against and nowhere
                for `align` to move the text, so an auto-sized label
                breaks only where the text itself says to.
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
        self._lines: list[str] = [text]
        self._line_height = 0
        # Wrapping costs one measurement per word, and `render` measures
        # every frame, so the result is kept until something it depends on
        # moves. A static HUD label re-wraps once, not sixty times a
        # second. The renderer is part of the key because two backends can
        # have different fonts loaded at the same size.
        self._wrap_key: tuple[Any, ...] | None = None

    @property
    def lines(self) -> list[str]:
        """The text as it will be drawn, one entry per rendered line.

        Empty until the first `measure()`, because breaking the text needs
        a renderer to measure candidates with.
        """
        return list(self._lines)

    @property
    def line_height(self) -> int:
        """The vertical step between rendered lines, in pixels."""
        return self._line_height

    def measure(self, renderer: UIRenderer) -> None:
        """Break the text into lines and size the rect to hold them.

        A fixed-width label holds its width and takes its height from the
        number of lines; an auto-sizing one takes its width from the
        widest line. Both used to take the height from a single
        `get_text_size` call, which is wrong for any text that occupies
        more than one line -- and newlines already did, because
        `get_text_size` ignores them and `draw_text` honours them.
        """
        key = (
            self.text,
            self.font_size,
            None if self._auto_size else self.rect.width,
            id(renderer),
        )
        if key != self._wrap_key:
            self._lines = wrap_text(
                self.text,
                None if self._auto_size else int(self.rect.width),
                lambda candidate: renderer.get_text_size(candidate, self.font_size)[0],
            )
            self._wrap_key = key

        # Measured from the empty string, so the step between lines is a
        # property of the font rather than of whichever glyphs a line
        # happens to contain. Both shipped backends answer `font.size`,
        # whose height is constant at a given size -- "aaa", "ÀÉÇ" and
        # "" all measure 18 at size 16 -- so this is defensive rather
        # than currently load-bearing. It is still the right call: the
        # protocol promises nothing about the height, a FreeType-backed
        # measurer would return the ink extent, and a label whose lines
        # advanced by different amounts depending on their accents is a
        # bug nobody would look for. `tests/test_ui_components.py` pins
        # it with a renderer that does vary.
        self._line_height = renderer.get_text_size("", self.font_size)[1]
        if self._auto_size:
            self.rect.width = max(
                (
                    renderer.get_text_size(line, self.font_size)[0]
                    for line in self._lines
                ),
                default=0,
            )
        self.rect.height = self._line_height * len(self._lines)

    def render(self, renderer: UIRenderer) -> None:
        """Draw one line per wrapped line, each positioned by `align`.

        Alignment is applied per line rather than to the block, which is
        what makes a centred paragraph look centred instead of looking
        like a left-aligned block that happens to start in the middle.
        """
        self.measure(renderer)

        final_color = self._custom_color or self.theme.colors.text
        for index, line in enumerate(self._lines):
            if not line:
                # Nothing to draw, but the line still takes its height.
                continue
            text_width, _ = renderer.get_text_size(line, self.font_size)
            if self.align == TextAlign.CENTER:
                x = self.rect.x + (self.rect.width - text_width) // 2
            elif self.align == TextAlign.RIGHT:
                x = self.rect.x + self.rect.width - text_width
            else:
                x = self.rect.x
            renderer.draw_text(
                line,
                Vector2(x, self.rect.y + index * self._line_height),
                final_color,
                self.font_size,
            )

    @property
    def custom_color(self) -> Color | None:
        """The colour set on this label, or None if it follows the theme."""
        return self._custom_color

    def set_color(self, color: Color | None) -> None:
        """Change the text colour, or pass None to follow the theme again.

        A label's colour was settable only at construction, so anything
        that recolours live -- a status line turning red during a pest
        outbreak, a value going negative -- had to reach into
        `_custom_color`. No layout is invalidated: a colour does not
        change the text's size.

        Args:
            color: The new colour, or None for the theme's body text.
        """
        self._custom_color = color

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
        self._lines = [text]
        self._wrap_key = None
        self.invalidate_layout()
