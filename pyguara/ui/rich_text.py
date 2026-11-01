"""Inline styling: a markup parser, and wrapping that keeps each run's style.

Separate from `text_layout` on purpose. `Label` is in every demo and should not
grow a parser it never uses, so plain text stays `wrap_text` and this sits beside
it, built the same way: pure functions over a measuring callback, testable
against arithmetic instead of whatever font the host has installed.

The markup is BBCode-style, chosen because it spells colour and size naturally
and never collides with the punctuation of ordinary dialogue:

```text
[b]bold[/b] [i]italic[/i] [color=#e2621f]hot[/color] [size=24]big[/size]
```

Tags nest, and must close in order. `[[` is a literal `[`. A malformed string
raises `MarkupError` rather than drawing its own tags at the player, so anything
a player typed goes through `escape_markup` first.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace

from pyguara.common.types import Color

__all__ = [
    "MarkupError",
    "Span",
    "SpanStyle",
    "StyledLine",
    "escape_markup",
    "parse_markup",
    "plain_text",
    "wrap_spans",
]


class MarkupError(ValueError):
    """A rich-text string does not parse."""


@dataclass(frozen=True)
class SpanStyle:
    """How one run of text is drawn.

    Attributes:
        color: The colour, or None for the widget's own.
        size: The font size, or None for the widget's own.
        bold: Whether it is bold.
        italic: Whether it is italic.
    """

    color: Color | None = None
    size: int | None = None
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class Span:
    """A run of text in one style.

    Attributes:
        text: The text.
        style: How it is drawn.
    """

    text: str
    style: SpanStyle = SpanStyle()


@dataclass(frozen=True)
class StyledLine:
    """One line as it will be drawn.

    Attributes:
        spans: The runs, left to right, with neighbours of one style merged so
            each is measured and drawn whole. Empty for a blank line.
        width: The line's width in pixels.
    """

    spans: tuple[Span, ...]
    width: int


MeasureSpan = Callable[[str, SpanStyle], int]
"""Returns the pixel width a string would be drawn at in a style."""


def escape_markup(text: str) -> str:
    """Make text safe to place inside markup, drawing exactly as written.

    For anything markup did not author, such as a player's name, which would
    otherwise raise on a stray `[`, or restyle the dialogue it appears in.

    Args:
        text: Any text.

    Returns:
        Markup that parses back to `text`.
    """
    return text.replace("[", "[[")


def plain_text(spans: Iterable[Span]) -> str:
    """Return the text of some spans, with the styling gone.

    Args:
        spans: The spans.

    Returns:
        Their text, joined.
    """
    return "".join(span.text for span in spans)


def parse_markup(markup: str) -> list[Span]:
    """Parse a marked-up string into styled runs.

    Args:
        markup: The string.

    Returns:
        The runs, in order, with neighbours of one style merged.

    Raises:
        MarkupError: For an unknown tag, a bad value, a close that does not match
            the open tag, or a tag left open. It says where.
    """
    spans: list[Span] = []
    # Each entry is the tag's name, and the style in force once it is open.
    stack: list[tuple[str, SpanStyle]] = []
    style = SpanStyle()
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            spans.append(Span("".join(buffer), style))
            buffer.clear()

    index = 0
    while index < len(markup):
        char = markup[index]
        if char != "[":
            buffer.append(char)
            index += 1
            continue
        if markup.startswith("[[", index):
            buffer.append("[")
            index += 2
            continue

        end = markup.find("]", index)
        if end == -1:
            raise MarkupError(
                f"Unclosed '[' at position {index} of {markup!r}. A literal "
                "bracket is written '[['."
            )
        tag = markup[index + 1 : end]
        flush()
        if tag.startswith("/"):
            name = tag[1:]
            if not stack or stack[-1][0] != name:
                expected = f"[/{stack[-1][0]}]" if stack else "no closing tag"
                raise MarkupError(
                    f"[/{name}] at position {index} of {markup!r}, where "
                    f"{expected} was expected."
                )
            stack.pop()
            style = stack[-1][1] if stack else SpanStyle()
        else:
            name, style = _open_tag(tag, style, index, markup)
            stack.append((name, style))
        index = end + 1

    flush()
    if stack:
        raise MarkupError(f"[{stack[-1][0]}] is never closed in {markup!r}.")
    return _merged(spans)


def _open_tag(
    tag: str, style: SpanStyle, index: int, markup: str
) -> tuple[str, SpanStyle]:
    """Apply an opening tag to the style in force.

    Args:
        tag: What was between the brackets.
        style: The style in force.
        index: Where the tag starts, for the error.
        markup: The whole string, for the error.

    Returns:
        The tag's name, and the new style.

    Raises:
        MarkupError: For an unknown tag or a bad value.
    """
    name, has_value, value = tag.partition("=")
    if not has_value:
        if name == "b":
            return name, replace(style, bold=True)
        if name == "i":
            return name, replace(style, italic=True)
    elif name == "color":
        try:
            return name, replace(style, color=Color.from_hex(value))
        except ValueError:
            raise MarkupError(
                f"[{tag}] at position {index} of {markup!r}: expected a colour "
                "like #e2621f."
            ) from None
    elif name == "size":
        if value.isdigit() and int(value) > 0:
            return name, replace(style, size=int(value))
        raise MarkupError(
            f"[{tag}] at position {index} of {markup!r}: expected a positive "
            "whole number."
        )
    raise MarkupError(
        f"Unknown tag [{tag}] at position {index} of {markup!r}. The tags are "
        "[b], [i], [color=#rrggbb] and [size=N]; a literal bracket is '[['."
    )


def _merged(spans: Iterable[Span]) -> list[Span]:
    """Join neighbouring runs of one style, and drop empty ones.

    Kerning only happens inside a single measurement, so a run split in two for
    no visible reason would measure and draw differently from itself whole.
    """
    merged: list[Span] = []
    for span in spans:
        if not span.text:
            continue
        if merged and merged[-1].style == span.style:
            merged[-1] = Span(merged[-1].text + span.text, span.style)
        else:
            merged.append(span)
    return merged


def _width(parts: Sequence[Span], measure: MeasureSpan) -> int:
    """Measure runs as they will be drawn, which is merged."""
    return sum(measure(run.text, run.style) for run in _merged(parts))


def wrap_spans(
    spans: Sequence[Span], width: int | None, measure: MeasureSpan
) -> list[StyledLine]:
    r"""Break styled runs into the lines that fit `width`.

    The same rules as `text_layout.wrap_text`, which a test pins by comparing the
    two on unstyled text: greedy, explicit newlines always split, runs of spaces
    survive, and a word too long for a line breaks mid-word. Styled, a word may
    span several runs (`[b]un[/b]believable` is one word), and a break inside a
    run keeps the style on both sides.

    Args:
        spans: The runs.
        width: The line width in pixels, or None to split on newlines only.
        measure: Measures a string's pixel width in a style.

    Returns:
        At least one line.
    """
    lines: list[StyledLine] = []
    for paragraph in _paragraphs(spans):
        if width is None:
            merged = _merged(paragraph)
            lines.append(StyledLine(tuple(merged), _width(merged, measure)))
        else:
            lines.extend(_wrap_paragraph(paragraph, width, measure))
    return lines


def _paragraphs(spans: Sequence[Span]) -> list[list[Span]]:
    r"""Split runs at explicit newlines, normalising `\r\n` and `\r` first."""
    paragraphs: list[list[Span]] = [[]]
    for span in spans:
        text = span.text.replace("\r\n", "\n").replace("\r", "\n")
        head, *rest = text.split("\n")
        if head:
            paragraphs[-1].append(Span(head, span.style))
        for part in rest:
            paragraphs.append([Span(part, span.style)] if part else [])
    return paragraphs


def _words(paragraph: Sequence[Span]) -> list[tuple[Span | None, list[Span]]]:
    """Split a paragraph at spaces, keeping the style each space was written in.

    Returns:
        Each word's preceding space, or None for the first, and the word's runs.
        A word may be empty, which is how a run of spaces survives.
    """
    words: list[tuple[Span | None, list[Span]]] = [(None, [])]
    for span in paragraph:
        head, *rest = span.text.split(" ")
        if head:
            words[-1][1].append(Span(head, span.style))
        for part in rest:
            pieces = [Span(part, span.style)] if part else []
            words.append((Span(" ", span.style), pieces))
    return words


def _wrap_paragraph(
    paragraph: Sequence[Span], width: int, measure: MeasureSpan
) -> list[StyledLine]:
    """Greedily break one newline-free paragraph."""
    lines: list[StyledLine] = []
    current: list[Span] = []

    def finish() -> None:
        merged = _merged(current)
        lines.append(StyledLine(tuple(merged), _width(merged, measure)))
        current.clear()

    for space, word in _words(paragraph):
        candidate = [*current, space, *word] if current and space else list(word)
        if _width(candidate, measure) <= width:
            current[:] = candidate
            continue

        if current:
            finish()

        head, tail = _split_word(word, width, measure)
        while tail:
            current[:] = head
            finish()
            head, tail = _split_word(tail, width, measure)
        current[:] = head

    finish()
    return lines


def _split_word(
    word: list[Span], width: int, measure: MeasureSpan
) -> tuple[list[Span], list[Span]]:
    """Cut a word's runs at the last character that still fits.

    Like `text_layout.split_oversized_word`, the head always holds at least one
    character, so a width too narrow for any glyph shows the mistake instead of
    looping forever.

    Returns:
        `(head, tail)`, where `tail` is empty if the whole word fits.
    """
    if _width(word, measure) <= width:
        return word, []
    total = sum(len(span.text) for span in word)
    cut = 1
    while cut < total and _width(_take(word, cut + 1)[0], measure) <= width:
        cut += 1
    return _take(word, cut)


def _take(word: list[Span], count: int) -> tuple[list[Span], list[Span]]:
    """Divide runs after `count` characters, keeping each side's style."""
    head: list[Span] = []
    tail: list[Span] = []
    remaining = count
    for span in word:
        if remaining >= len(span.text):
            head.append(span)
            remaining -= len(span.text)
        elif remaining > 0:
            head.append(Span(span.text[:remaining], span.style))
            tail.append(Span(span.text[remaining:], span.style))
            remaining = 0
        else:
            tail.append(span)
    return head, tail
