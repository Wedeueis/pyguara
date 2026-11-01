"""A label with inline styling."""

from typing import Any

from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget
from pyguara.ui.rich_text import (
    Span,
    SpanStyle,
    StyledLine,
    parse_markup,
    plain_text,
    wrap_spans,
)
from pyguara.ui.types import TextAlign


class RichLabel(Widget):
    """Displays text with inline bold, italic, colour and size.

    ```python
    RichLabel("[b]Tamanduá[/b] takes [color=#e2621f]12 fire[/color] damage")
    ```

    See `pyguara.ui.rich_text` for the markup. Its own widget, not a mode on
    `Label`, because the plain label is in every demo and has no use for a parser.

    A string that does not parse raises `MarkupError` when it is set, not when it
    is first drawn. Anything a player typed goes through `escape_markup` first.

    On a line of mixed sizes, runs share a bottom edge, which is close to a shared
    baseline but not the same: the renderer reports a line's height, not a font's
    ascent.
    """

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
            text: The marked-up text.
            position: Top-left corner.
            font_size: Font size for text that does not state its own.
            color: Colour for text that does not state its own, or None for the
                theme's body text.
            width: A fixed width to wrap inside, or None to auto-size to the
                text, breaking only at its own newlines.
            align: Where each line sits inside `width`.

        Raises:
            MarkupError: If `text` does not parse.
        """
        super().__init__(position, Vector2(width if width is not None else 0, 0))
        self.font_size = font_size
        self.color = color
        self.align = align
        self._auto_size = width is None
        self._spans = parse_markup(text)
        self._text = text
        self._lines: list[StyledLine] = []
        self._line_heights: list[int] = []
        self._line_tops: list[int] = []
        # Wrapping measures per word and `render` measures every frame, so the
        # result is kept until something it depends on moves.
        self._wrap_key: tuple[Any, ...] | None = None

    @property
    def text(self) -> str:
        """The marked-up text."""
        return self._text

    @text.setter
    def text(self, value: str) -> None:
        self._spans = parse_markup(value)
        self._text = value
        self._wrap_key = None

    @property
    def plain_text(self) -> str:
        """The text with its markup gone, for a screen reader or a log."""
        return plain_text(self._spans)

    @property
    def lines(self) -> list[StyledLine]:
        """The lines as they will be drawn. Empty until the first `measure()`."""
        return list(self._lines)

    def _size_of(self, style: SpanStyle) -> int:
        return style.size if style.size is not None else self.font_size

    def _span_size(
        self, renderer: UIRenderer, text: str, style: SpanStyle
    ) -> tuple[int, int]:
        return renderer.get_text_size(
            text, self._size_of(style), bold=style.bold, italic=style.italic
        )

    def measure(self, renderer: UIRenderer) -> None:
        """Wrap the text if anything it depends on moved, and size the rect."""
        key = (
            self._text,
            self.font_size,
            None if self._auto_size else self.rect.width,
            id(renderer),
        )
        if key == self._wrap_key:
            return
        self._wrap_key = key

        self._lines = wrap_spans(
            self._spans,
            None if self._auto_size else int(self.rect.width),
            lambda text, style: self._span_size(renderer, text, style)[0],
        )

        # Each line is as tall as its largest run, so `[size=32]` in a paragraph
        # pushes the next line down rather than through it.
        self._line_heights = [self._height_of(line, renderer) for line in self._lines]
        self._line_tops = []
        top = 0
        for line in self._lines:
            self._line_tops.append(top)
            top += max(
                (renderer.get_line_height(self._size_of(s.style)) for s in line.spans),
                default=renderer.get_line_height(self.font_size),
            )
        # The last line has no line after it, so it takes no leading.
        last = self._line_tops[-1] + self._line_heights[-1]
        self.rect.height = last
        if self._auto_size:
            self.rect.width = max((line.width for line in self._lines), default=0)

    def _height_of(self, line: StyledLine, renderer: UIRenderer) -> int:
        """Return how tall a line's largest run is."""
        if not line.spans:
            return renderer.get_text_size("", self.font_size)[1]
        return max(self._span_size(renderer, "", span.style)[1] for span in line.spans)

    def render(self, renderer: UIRenderer) -> None:
        """Draw every line, run by run, with an x cursor."""
        self.measure(renderer)

        default_color = self.color or self.theme.colors.text
        for line, top, height in zip(
            self._lines, self._line_tops, self._line_heights, strict=True
        ):
            x = self._line_x(line)
            for span in line.spans:
                self._draw_span(renderer, span, x, top, height, default_color)
                x += self._span_size(renderer, span.text, span.style)[0]

    def _line_x(self, line: StyledLine) -> float:
        """Return where a line starts, by `align`."""
        if self.align == TextAlign.CENTER:
            return self.rect.x + (self.rect.width - line.width) // 2
        if self.align == TextAlign.RIGHT:
            return self.rect.x + self.rect.width - line.width
        return self.rect.x

    def _draw_span(
        self,
        renderer: UIRenderer,
        span: Span,
        x: float,
        top: int,
        line_height: int,
        default_color: Color,
    ) -> None:
        """Draw one run, standing on the line's bottom edge."""
        style = span.style
        height = self._span_size(renderer, "", style)[1]
        renderer.draw_text(
            span.text,
            Vector2(x, self.rect.y + top + line_height - height),
            style.color or default_color,
            self._size_of(style),
            bold=style.bold,
            italic=style.italic,
        )
