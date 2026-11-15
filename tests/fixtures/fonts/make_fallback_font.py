"""Build `PyguaraTestCJK.ttf`, the tiny font the fallback tests draw with.

Liberation Sans has no CJK glyphs, so a test needs a face that does, and a
real Noto Sans CJK is 16 MB. This one has five glyphs, each a different
filled shape so a test can tell which face drew a character:

- U+4E00 一, U+3042 あ, U+AC00 가 and U+3002 。, which Liberation lacks;
- U+0041 A, which Liberation has: the fallback must not be used for it.

Rebuild with (fontTools is not a project dependency):

    uvx --from fonttools python tests/fixtures/fonts/make_fallback_font.py
"""

from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

UNITS = 1000


def box(left: int, bottom: int, right: int, top: int):
    pen = TTGlyphPen(None)
    pen.moveTo((left, bottom))
    pen.lineTo((left, top))
    pen.lineTo((right, top))
    pen.lineTo((right, bottom))
    pen.closePath()
    return pen.glyph()


def empty():
    return TTGlyphPen(None).glyph()


GLYPHS = {
    ".notdef": (empty(), 500),
    "A": (box(100, 0, 500, 700), 600),  # a solid block, unlike Liberation's A
    "uni4E00": (box(50, 330, 950, 430), 1000),  # one horizontal bar: 一
    "uni3042": (box(150, 0, 850, 800), 1000),  # a tall block: あ
    "uniAC00": (box(100, 100, 900, 600), 1000),  # a wide block: 가
    "uni3002": (box(100, 0, 300, 200), 1000),  # a small square low: 。
}
CMAP = {
    0x41: "A",
    0x4E00: "uni4E00",
    0x3042: "uni3042",
    0xAC00: "uniAC00",
    0x3002: "uni3002",
}

builder = FontBuilder(UNITS, isTTF=True)
builder.setupGlyphOrder(list(GLYPHS))
builder.setupCharacterMap(CMAP)
builder.setupGlyf({name: glyph for name, (glyph, _) in GLYPHS.items()})
builder.setupHorizontalMetrics(
    {name: (advance, 0) for name, (_, advance) in GLYPHS.items()}
)
builder.setupHorizontalHeader(ascent=880, descent=-120)
builder.setupNameTable({"familyName": "Pyguara Test CJK", "styleName": "Regular"})
builder.setupOS2(
    sTypoAscender=880, sTypoDescender=-120, usWinAscent=880, usWinDescent=120
)
builder.setupPost()
builder.save(str(Path(__file__).with_name("PyguaraTestCJK.ttf")))
