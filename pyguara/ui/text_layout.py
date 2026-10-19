r"""Breaking a string into the lines a renderer will actually draw.

Pure functions over a measuring callback, deliberately: wrapping needs to
know how wide a candidate line is, and that is the only thing it needs a
renderer for. Keeping the measurement at arm's length means the algorithm
can be tested against a predictable fake rather than against whatever font
the host happens to have installed.

Two things made this necessary rather than decorative.

`Label` had a `width` and made exactly one `draw_text` call, so text
longer than that width simply ran past it -- 423 px of text drawn through
a 150 px label, overflowing by 273 px and over whatever sat beside it.

Worse, a `UIRenderer`'s measure and draw **disagree about newlines**.
`get_text_size` is `pygame.font.Font.size`, which measures a single line
and ignores `\\n`; `draw_text` is `Font.render`, which honours it. So
`"first line\\nsecond line"` measured 146x18 and drew 79x38: the width too
wide by 67 px and the height exactly half. A layout that stacks siblings
from the measured height puts the next widget on top of the second line.
Splitting the text here and drawing one line per call is what makes the
two agree.
"""

from collections.abc import Callable

__all__ = ["split_oversized_word", "wrap_text"]

MeasureWidth = Callable[[str], int]
"""Returns the pixel width a string would be drawn at."""


def split_oversized_word(
    word: str, width: int, measure: MeasureWidth
) -> tuple[str, str]:
    """Cut `word` at the last character that still fits in `width`.

    Args:
        word: The word to cut. Must be non-empty.
        width: The line width in pixels.
        measure: Measures a candidate's pixel width.

    Returns:
        `(head, tail)`, where `head` fits and `tail` is what is left, or
        `(word, "")` when the whole word fits. **`head` always holds at
        least one character**, even when a single character does not fit:
        a width too narrow for any glyph is a layout mistake, and
        returning an empty head for it would make the caller loop forever
        rather than show the mistake.
    """
    if measure(word) <= width:
        return word, ""
    cut = 1
    while cut < len(word) and measure(word[: cut + 1]) <= width:
        cut += 1
    return word[:cut], word[cut:]


def wrap_text(text: str, width: int | None, measure: MeasureWidth) -> list[str]:
    r"""Break `text` into the lines that fit `width`.

    Explicit newlines always split, `width` or no `width` -- they are the
    author asking for a break rather than the layout discovering one. A
    run of them produces empty lines, which are kept: a blank line between
    paragraphs is content.

    Greedy, not minimum-raggedness. A Knuth-Plass-style optimal break
    reads better in a book and is not worth a per-frame dynamic program
    for a HUD; nothing here precludes adding one later behind the same
    signature.

    Args:
        text: The string to break. `\\r\\n` and `\\r` are normalised to
            `\\n` first, so a file read in text mode on one platform and
            binary on another wraps the same way instead of leaving a
            stray glyph at every line end.
        width: The line width in pixels, or None to split on explicit
            newlines only -- which is what an auto-sizing label wants,
            since its own width is whatever the text turns out to be.
        measure: Measures a candidate line's pixel width.

    Returns:
        At least one line; `""` wraps to `[""]`, not to `[]`, so a caller
        can rely on the line count being the height in lines.
    """
    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    if width is None:
        return normalised.split("\n")

    lines: list[str] = []
    for paragraph in normalised.split("\n"):
        lines.extend(_wrap_paragraph(paragraph, width, measure))
    return lines


def _wrap_paragraph(paragraph: str, width: int, measure: MeasureWidth) -> list[str]:
    """Greedily break one newline-free paragraph.

    Args:
        paragraph: The text, containing no newlines.
        width: The line width in pixels.
        measure: Measures a candidate line's pixel width.

    Returns:
        At least one line.
    """
    lines: list[str] = []
    current = ""

    # Split on single spaces rather than `str.split()`, which collapses
    # runs of whitespace -- "10  20" is a column alignment somebody meant.
    for word in paragraph.split(" "):
        candidate = f"{current} {word}" if current else word
        if measure(candidate) <= width:
            current = candidate
            continue

        if current:
            lines.append(current)
            current = ""

        # The word now starts a line of its own. If it still does not fit,
        # it is broken mid-word: the alternative is one line overflowing
        # the label, which is the behaviour being fixed.
        head, tail = split_oversized_word(word, width, measure)
        while tail:
            lines.append(head)
            head, tail = split_oversized_word(tail, width, measure)
        current = head

    lines.append(current)
    return lines
