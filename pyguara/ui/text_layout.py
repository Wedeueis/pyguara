"""Breaking a string into the lines a renderer will actually draw.

Pure functions over a measuring callback: wrapping needs to know how
wide a candidate line is and nothing else from a renderer, so it can
be tested against a fake.

A renderer's `get_text_size` measures a single line and ignores
newlines, while `draw_text` honours them. Splitting the text here and
drawing one line per call makes the measured size and the drawn size
agree.
"""

from collections.abc import Callable

__all__ = ["break_offsets", "caret_index_at", "split_oversized_word", "wrap_text"]

MeasureWidth = Callable[[str], int]
"""Returns the pixel width a string would be drawn at."""


# -- Breaking without spaces -------------------------------------------------
#
# Chinese and Japanese are written without spaces between words, so a line
# may break between any two of their characters -- except where the kinsoku
# rules forbid it: a line may not start with closing punctuation, a small
# kana or a prolonged-sound mark, nor end with an opening bracket. Korean
# puts spaces between words and wraps on them, as Latin does. This is the
# part of Unicode's line breaking (UAX #14) those languages need, not all
# of it.

_CJK_RANGES = (
    (0x2E80, 0x2FDF),  # CJK radicals, Kangxi radicals
    (0x3000, 0x30FF),  # CJK symbols and punctuation, hiragana, katakana
    (0x3100, 0x312F),  # bopomofo
    (0x31F0, 0x31FF),  # katakana phonetic extensions
    (0x3400, 0x4DBF),  # CJK extension A
    (0x4E00, 0x9FFF),  # CJK unified ideographs
    (0xF900, 0xFAFF),  # CJK compatibility ideographs
    (0xFE30, 0xFE4F),  # CJK compatibility forms
    (0xFF00, 0xFFEF),  # half-width and full-width forms
    (0x20000, 0x3FFFF),  # CJK extensions B and later
)

_NO_LINE_START = frozenset(
    "、。，．・：；？！ー）」』】〕〉》〙〗］｝〟’”〜～…‥々〻ゝゞヽヾ゛゜"
    "ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ"
    "ㇰㇱㇲㇳㇴㇵㇶㇷㇸㇹㇺㇻㇼㇽㇾㇿｧｨｩｪｫｬｭｮｯｰ"
    "!%),.:;?]}"
)
_NO_LINE_END = frozenset("（「『【〔〈《〘〖［｛〝‘“([{")


def _is_cjk(character: str) -> bool:
    code = ord(character)
    return any(low <= code <= high for low, high in _CJK_RANGES)


def break_offsets(word: str) -> list[int]:
    """Return where `word`, which has no spaces, may break across lines.

    Between two Chinese or Japanese characters, or between one of them and
    Latin text, unless the kinsoku rules forbid it. Never inside a Latin or
    Korean word.

    Args:
        word: A run of text with no spaces in it.

    Returns:
        The indices `i`, `0 < i < len(word)`, where a line may end before
        `word[i]`, in order.
    """
    return [
        index
        for index in range(1, len(word))
        if (_is_cjk(word[index - 1]) or _is_cjk(word[index]))
        and word[index] not in _NO_LINE_START
        and word[index - 1] not in _NO_LINE_END
    ]


def _pieces(word: str) -> list[str]:
    """Split a space-free word at its break offsets."""
    offsets = break_offsets(word)
    if not offsets:
        return [word]
    bounds = [0, *offsets, len(word)]
    return [word[start:end] for start, end in zip(bounds, bounds[1:], strict=False)]


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
    # Chinese and Japanese words are cut further into the pieces a line may
    # break between, which join with nothing rather than a space.
    for word in paragraph.split(" "):
        for index, piece in enumerate(_pieces(word)):
            joiner = " " if index == 0 else ""
            current = _place(piece, joiner, current, lines, width, measure)

    lines.append(current)
    return lines


def _place(
    piece: str,
    joiner: str,
    current: str,
    lines: list[str],
    width: int,
    measure: MeasureWidth,
) -> str:
    """Add `piece` to the line being built, or start a new one with it.

    Returns:
        The line now being built; finished lines are appended to `lines`.
    """
    candidate = f"{current}{joiner}{piece}" if current else piece
    if measure(candidate) <= width:
        return candidate

    if current:
        lines.append(current)

    # The piece now starts a line of its own. If it still does not fit, it
    # is broken mid-word: the alternative is one line overflowing the label,
    # which is the behaviour being fixed.
    head, tail = split_oversized_word(piece, width, measure)
    while tail:
        lines.append(head)
        head, tail = split_oversized_word(tail, width, measure)
    return head


def caret_index_at(text: str, offset: int, measure: MeasureWidth) -> int:
    """Return the caret index nearest `offset` pixels into `text`.

    A caret sits between characters, so the answer is a boundary. The left
    half of a glyph puts the caret before it and the right half after.

    Linear in the length of the text, measuring each prefix. Bisection is
    not used: with kerning, prefix widths need not be monotonic.

    Args:
        text: The string the caret is being placed in.
        offset: Pixels from the start of the text. Values outside the
            text clamp to the ends rather than being an error -- a drag
            that leaves the widget is an ordinary thing to do.
        measure: Measures a prefix's pixel width.

    Returns:
        An index in `0..len(text)`.
    """
    if offset <= 0 or not text:
        return 0
    previous = 0
    for index in range(1, len(text) + 1):
        current = measure(text[:index])
        if offset < (previous + current) / 2:
            return index - 1
        previous = current
    return len(text)
