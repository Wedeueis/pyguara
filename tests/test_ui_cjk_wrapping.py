"""Chinese and Japanese wrap between characters; Korean and Latin on spaces.

Chinese and Japanese are written without spaces, so a wrapper that only
breaks at spaces sees one enormous word and cuts it wherever it overflows,
which can start a line with `。` or end one with `「`. The kinsoku rules say
where a line may not start or end.

Every character measures 10 px here, so a width of 40 fits four.
"""

from __future__ import annotations

import pytest

from pyguara.ui.rich_text import Span, SpanStyle, parse_markup, plain_text, wrap_spans
from pyguara.ui.text_case import case_language, lower, set_case_language, upper
from pyguara.ui.text_layout import break_offsets, wrap_text


def _ten(text: str) -> int:
    return 10 * len(text)


def _styled(text: str, style: SpanStyle) -> int:
    return len(text) * (15 if style.bold else 10)


# --------------------------------------------------------------------------- #
# Where a line may break                                                       #
# --------------------------------------------------------------------------- #


def test_between_han_and_kana_characters() -> None:
    assert break_offsets("日本語です") == [1, 2, 3, 4]


def test_not_inside_latin_or_korean_words() -> None:
    assert break_offsets("Reclaimer") == []
    assert break_offsets("안녕하세요") == []


def test_between_cjk_and_latin() -> None:
    assert break_offsets("第3章") == [1, 2]
    assert break_offsets("Steamで") == [5]


def test_never_before_closing_punctuation_or_small_kana() -> None:
    # 。 、 」 ッ ー may not start a line.
    assert break_offsets("終わり。") == [1, 2]
    assert break_offsets("「はい」と") == [2, 4]
    assert break_offsets("ゲーム") == [2]
    assert break_offsets("ちょっと") == [3]


def test_never_after_opening_brackets() -> None:
    assert break_offsets("前「後") == [1]


# --------------------------------------------------------------------------- #
# Wrapping                                                                     #
# --------------------------------------------------------------------------- #


def test_japanese_wraps_between_characters() -> None:
    assert wrap_text("日本語のテキストです", 40, _ten) == [
        "日本語の",
        "テキスト",
        "です",
    ]


def test_a_line_does_not_start_with_a_full_stop() -> None:
    # "ト。" is one unit: 。 may not start a line, so it never parts from ト.
    assert wrap_text("これはテスト。", 40, _ten) == ["これはテ", "スト。"]
    assert wrap_text("これはテスト。", 60, _ten) == ["これはテス", "ト。"]


def test_chinese_with_punctuation() -> None:
    assert wrap_text("你好，世界！欢迎", 40, _ten) == ["你好，世", "界！欢迎"]
    # Two to a line: "好，" and "界！" stay together.
    assert wrap_text("你好，世界！欢迎", 20, _ten) == [
        "你",
        "好，",
        "世",
        "界！",
        "欢迎",
    ]


def test_korean_wraps_on_its_spaces() -> None:
    assert wrap_text("안녕 하세요 세계", 60, _ten) == ["안녕 하세요", "세계"]


def test_latin_inside_japanese_stays_whole() -> None:
    assert wrap_text("ゲームReclaimerを", 100, _ten) == ["ゲーム", "Reclaimerを"]


def test_latin_text_wraps_as_before() -> None:
    text = "the quick brown fox jumps"
    assert wrap_text(text, 100, _ten) == ["the quick", "brown fox", "jumps"]


@pytest.mark.parametrize(
    "text",
    [
        "日本語のテキストです",
        "これはテスト。",
        "你好，世界！欢迎",
        "ゲームReclaimerを",
        "「はい」と言った",
    ],
)
@pytest.mark.parametrize("width", [30, 40, 70])
def test_rich_text_wraps_cjk_exactly_as_plain_text(text: str, width: int) -> None:
    styled = wrap_spans([Span(text)], width, _styled)
    assert [plain_text(line.spans) for line in styled] == wrap_text(text, width, _ten)


def test_a_style_change_inside_japanese_keeps_both_styles() -> None:
    lines = wrap_spans(parse_markup("日本[b]語の[/b]テキスト"), 40, _styled)
    assert [plain_text(line.spans) for line in lines] == ["日本語", "のテキ", "スト"]
    assert any(span.style.bold for span in lines[0].spans)


# --------------------------------------------------------------------------- #
# Turkish casing                                                               #
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _english_after():
    yield
    set_case_language("en")


def test_english_is_the_default() -> None:
    assert case_language() == "en"
    assert upper("dikkat") == "DIKKAT"


def test_turkish_dotted_and_dotless_i() -> None:
    set_case_language("tr")
    assert upper("dikkat ılık") == "DİKKAT ILIK"
    assert lower("DİKKAT ILIK") == "dikkat ılık"


def test_a_region_does_not_matter() -> None:
    set_case_language("tr-TR")
    assert upper("i") == "İ"
    set_case_language("az")  # Azerbaijani has the same i
    assert upper("i") == "İ"


def test_the_design_system_button_uppercases_for_the_language() -> None:
    from pyguara.ui.design_system.components import case_label

    set_case_language("tr")
    assert case_label("başla", uppercase=True) == "BAŞLA"
    assert case_label("iptal", uppercase=True) == "İPTAL"
    assert case_label("iptal", uppercase=False) == "iptal"
