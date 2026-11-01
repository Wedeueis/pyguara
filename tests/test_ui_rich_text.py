"""Rich text: the markup, wrapping that keeps a run's style, and `RichLabel` (#340)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pygame
import pytest

from pyguara.common.types import Color, Vector2
from pyguara.graphics.backends.pygame.ui_renderer import PygameUIRenderer
from pyguara.ui.builder import UIBuilder
from pyguara.ui.components.rich_label import RichLabel
from pyguara.ui.rich_text import (
    MarkupError,
    Span,
    SpanStyle,
    escape_markup,
    parse_markup,
    plain_text,
    wrap_spans,
)
from pyguara.ui.text_layout import wrap_text
from pyguara.ui.types import TextAlign

BOLD = SpanStyle(bold=True)
ITALIC = SpanStyle(italic=True)
ORANGE = Color(226, 98, 31)


def _measure(text: str, style: SpanStyle) -> int:
    """10 px a character, 15 when bold, so a style visibly changes a width."""
    return len(text) * (15 if style.bold else 10)


def _texts(lines: Any) -> list[str]:
    return [plain_text(line.spans) for line in lines]


class TestParsing:
    def test_plain_text_is_one_run(self) -> None:
        assert parse_markup("hello") == [Span("hello")]

    def test_empty_text_is_no_runs(self) -> None:
        assert parse_markup("") == []

    def test_bold(self) -> None:
        assert parse_markup("a [b]b[/b] c") == [
            Span("a "),
            Span("b", BOLD),
            Span(" c"),
        ]

    def test_tags_nest(self) -> None:
        assert parse_markup("[b]a[i]b[/i]c[/b]") == [
            Span("a", BOLD),
            Span("b", SpanStyle(bold=True, italic=True)),
            Span("c", BOLD),
        ]

    def test_color(self) -> None:
        [span] = parse_markup("[color=#e2621f]hot[/color]")

        assert span.style.color == ORANGE

    def test_size(self) -> None:
        [span] = parse_markup("[size=24]big[/size]")

        assert span.style.size == 24

    def test_a_doubled_bracket_is_a_literal(self) -> None:
        assert parse_markup("a[[1]") == [Span("a[1]")]

    def test_a_closing_bracket_alone_is_just_a_character(self) -> None:
        assert parse_markup("a]b") == [Span("a]b")]

    def test_empty_tags_leave_nothing(self) -> None:
        assert parse_markup("a[b][/b]c") == [Span("ac")]

    @pytest.mark.parametrize(
        ("markup", "message"),
        [
            ("[bold]a[/bold]", "Unknown tag"),
            ("[colour=#fff]a[/colour]", "Unknown tag"),
            ("[b]a", "never closed"),
            ("a[/b]", "no closing tag"),
            ("[b][i]a[/b][/i]", "expected"),
            ("[color=orange]a[/color]", "colour like"),
            ("[size=big]a[/size]", "positive"),
            ("[size=0]a[/size]", "positive"),
            ("[size=-3]a[/size]", "positive"),
            ("a [ b", "Unclosed"),
        ],
    )
    def test_a_malformed_string_says_what_is_wrong(
        self, markup: str, message: str
    ) -> None:
        with pytest.raises(MarkupError, match=message):
            parse_markup(markup)


class TestEscaping:
    @pytest.mark.parametrize(
        "text", ["[b]pwned[/b]", "a[1]", "[[", "]", "plain", "[", "[/b]"]
    )
    def test_anything_comes_back_exactly_as_written(self, text: str) -> None:
        assert plain_text(parse_markup(escape_markup(text))) == text

    def test_it_is_not_styled_by_what_it_contains(self) -> None:
        [span] = parse_markup(escape_markup("[b]x[/b]"))

        assert span.style == SpanStyle()


class TestWrapping:
    @pytest.mark.parametrize(
        "text",
        [
            "the quick brown fox jumps over the lazy dog",
            "short",
            "",
            "a  double  space",
            " leading",
            "trailing ",
            "one\ntwo\n\nfour",
            "windows\r\nnewline",
            "averyveryveryveryverylongwordindeed that wraps",
            "x " * 40,
        ],
    )
    @pytest.mark.parametrize("width", [40, 95, 200, None])
    def test_unstyled_it_is_exactly_wrap_text(
        self, text: str, width: int | None
    ) -> None:
        """The plain path is the reference, or two sets of rules would drift."""
        styled = wrap_spans([Span(text)] if text else [], width, _measure)
        plain = wrap_text(text, width, lambda s: _measure(s, SpanStyle()))

        assert _texts(styled) == plain

    def test_a_style_change_inside_a_word_is_not_a_place_to_break(self) -> None:
        spans = parse_markup("[b]un[/b]believable x")

        lines = wrap_spans(spans, 140, _measure)

        assert _texts(lines) == ["unbelievable", "x"]

    def test_a_break_keeps_the_style_on_both_sides(self) -> None:
        lines = wrap_spans(parse_markup("[b]one two[/b]"), 60, _measure)

        assert [line.spans for line in lines] == [
            (Span("one", BOLD),),
            (Span("two", BOLD),),
        ]

    def test_a_style_changes_what_fits(self) -> None:
        """Bold is wider here, so the same characters break differently."""
        assert _texts(wrap_spans(parse_markup("aaa bbb"), 70, _measure)) == ["aaa bbb"]
        assert _texts(wrap_spans(parse_markup("[b]aaa bbb[/b]"), 70, _measure)) == [
            "aaa",
            "bbb",
        ]

    def test_an_oversized_word_breaks_keeping_each_runs_style(self) -> None:
        lines = wrap_spans(parse_markup("aaaa[b]bbbb[/b]"), 60, _measure)

        assert lines[0].spans == (Span("aaaa"), Span("b", BOLD))
        assert plain_text(lines[-1].spans).endswith("b")
        assert all(line.width <= 60 for line in lines)
        assert "".join(_texts(lines)) == "aaaabbbb"

    def test_a_width_too_narrow_for_a_glyph_still_ends(self) -> None:
        lines = wrap_spans([Span("abc")], 1, _measure)

        assert _texts(lines) == ["a", "b", "c"]

    def test_a_newline_inside_a_run_keeps_its_style(self) -> None:
        lines = wrap_spans(parse_markup("[b]a\nb[/b]"), None, _measure)

        assert [line.spans for line in lines] == [
            (Span("a", BOLD),),
            (Span("b", BOLD),),
        ]

    def test_a_blank_line_is_kept(self) -> None:
        assert _texts(wrap_spans(parse_markup("a\n\nb"), None, _measure)) == [
            "a",
            "",
            "b",
        ]

    def test_a_line_reports_its_width_across_styles(self) -> None:
        [line] = wrap_spans(parse_markup("aa[b]bb[/b]"), None, _measure)

        assert line.width == 20 + 30


class _Recording:
    """A renderer whose metrics are arithmetic, recording what is drawn."""

    def __init__(self) -> None:
        self.drawn: list[dict[str, Any]] = []

    def get_text_size(
        self, text: str, size: int, *, bold: bool = False, italic: bool = False
    ) -> tuple[int, int]:
        per_char = 15 if bold else 10
        return (len(text) * per_char * size // 16, 20 * size // 16)

    def get_line_height(self, size: int) -> int:
        return 22 * size // 16

    def draw_text(
        self,
        text: str,
        position: Vector2,
        color: Color,
        size: int = 16,
        *,
        bold: bool = False,
        italic: bool = False,
    ) -> None:
        self.drawn.append(
            {
                "text": text,
                "x": position.x,
                "y": position.y,
                "color": color,
                "size": size,
                "bold": bold,
                "italic": italic,
            }
        )

    def __getattr__(self, name: str) -> Any:
        return MagicMock()


class TestRichLabel:
    def test_runs_are_drawn_left_to_right_each_in_its_style(self) -> None:
        renderer = _Recording()

        RichLabel("aa[b]bb[/b]cc", Vector2(5, 7)).render(renderer)  # type: ignore[arg-type]

        assert [(d["text"], d["x"], d["bold"]) for d in renderer.drawn] == [
            ("aa", 5, False),
            ("bb", 25, True),
            ("cc", 55, False),
        ]

    def test_a_run_with_no_colour_of_its_own_takes_the_labels(self) -> None:
        renderer = _Recording()
        label = RichLabel("a[color=#e2621f]b[/color]", color=Color(1, 2, 3))

        label.render(renderer)  # type: ignore[arg-type]

        assert renderer.drawn[0]["color"] == Color(1, 2, 3)
        assert renderer.drawn[1]["color"] == ORANGE

    def test_lines_step_by_the_fonts_advance(self) -> None:
        renderer = _Recording()

        RichLabel("a\nb", Vector2(0, 10)).render(renderer)  # type: ignore[arg-type]

        assert [d["y"] for d in renderer.drawn] == [10, 32]

    def test_a_large_run_pushes_the_next_line_down(self) -> None:
        renderer = _Recording()
        label = RichLabel("[size=32]A[/size]\nb")

        label.render(renderer)  # type: ignore[arg-type]

        assert renderer.drawn[1]["y"] == 44
        assert label.rect.height == 44 + 20

    def test_runs_of_different_sizes_share_a_bottom_edge(self) -> None:
        renderer = _Recording()

        RichLabel("a[size=32]B[/size]").render(renderer)  # type: ignore[arg-type]

        small, large = renderer.drawn
        assert small["y"] + 20 == large["y"] + 40

    def test_an_auto_sized_label_measures_across_styles(self) -> None:
        label = RichLabel("aa[b]bb[/b]")

        label.measure(_Recording())  # type: ignore[arg-type]

        assert (label.rect.width, label.rect.height) == (50, 20)

    def test_a_fixed_width_wraps(self) -> None:
        label = RichLabel("[b]one two[/b]", width=60)

        label.measure(_Recording())  # type: ignore[arg-type]

        assert len(label.lines) == 2
        assert label.rect.width == 60

    @pytest.mark.parametrize(
        ("align", "x"), [(TextAlign.CENTER, 40), (TextAlign.RIGHT, 80)]
    )
    def test_alignment_uses_the_whole_lines_width(
        self, align: TextAlign, x: int
    ) -> None:
        renderer = _Recording()

        RichLabel("a[b]b[/b]", width=105, align=align).render(renderer)  # type: ignore[arg-type]

        assert renderer.drawn[0]["x"] == x

    def test_bad_markup_raises_when_set_not_when_drawn(self) -> None:
        with pytest.raises(MarkupError):
            RichLabel("[b]a")

        label = RichLabel("fine")
        with pytest.raises(MarkupError):
            label.text = "[nope]"
        assert label.text == "fine"

    def test_changing_the_text_rewraps(self) -> None:
        renderer = _Recording()
        label = RichLabel("a")
        label.render(renderer)  # type: ignore[arg-type]

        label.text = "aaaa"
        label.measure(renderer)  # type: ignore[arg-type]

        assert label.rect.width == 40

    def test_it_exposes_the_text_without_markup(self) -> None:
        assert RichLabel("[b]a[/b]b").plain_text == "ab"

    def test_a_builder_makes_one(self) -> None:
        with UIBuilder() as ui:
            label = ui.rich_label("[b]a[/b]", font_size=20)

        assert isinstance(label, RichLabel)
        assert label.font_size == 20


class TestAgainstARealFont:
    """Through the real renderer, because bold has to reach the font."""

    @pytest.fixture
    def renderer(self) -> PygameUIRenderer:
        pygame.font.init()
        return PygameUIRenderer(pygame.Surface((400, 80), pygame.SRCALPHA))

    def test_bold_measures_at_least_as_wide(self, renderer: PygameUIRenderer) -> None:
        plain = renderer.get_text_size("Tamandua", 24)[0]

        assert renderer.get_text_size("Tamandua", 24, bold=True)[0] >= plain

    def test_styles_do_not_share_a_cached_font(
        self, renderer: PygameUIRenderer
    ) -> None:
        assert renderer._get_font(24) is not renderer._get_font(24, True, False)
        assert renderer._get_font(24, True, False) is not renderer._get_font(
            24, False, True
        )

    def test_a_coloured_run_reaches_the_surface_where_it_was_placed(self) -> None:
        pygame.font.init()
        surface = pygame.Surface((400, 40), pygame.SRCALPHA)
        renderer = PygameUIRenderer(surface)

        RichLabel("AAAA[color=#ff0000]BBBB[/color]", color=Color(0, 0, 255)).render(
            renderer
        )

        split = renderer.get_text_size("AAAA", 16)[0]
        colours = [
            (x, tuple(surface.get_at((x, y)))[:3])
            for x in range(surface.get_width())
            for y in range(surface.get_height())
            if surface.get_at((x, y)).a == 255
        ]
        assert any(c == (0, 0, 255) for x, c in colours if x < split)
        assert any(c == (255, 0, 0) for x, c in colours if x >= split)
        assert not any(c == (255, 0, 0) for x, c in colours if x < split)
