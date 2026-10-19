"""Tests for `pyguara.ui.text_layout`.

Every width here is measured by `_ten_px_per_character`, not by a font, so
a line of four characters is 40 px on any machine. Wrapping is an
algorithm; testing it against whatever font the host happens to have
installed would make these tests a measurement of Arial.
"""

from __future__ import annotations

import pytest

from pyguara.ui.text_layout import (
    caret_index_at,
    split_oversized_word,
    wrap_text,
)


def _ten_px_per_character(text: str) -> int:
    return len(text) * 10


class TestSplittingOnExplicitNewlines:
    """Author-placed breaks, which apply whether or not there is a width."""

    def test_no_width_splits_on_newlines_only(self) -> None:
        assert wrap_text("one\ntwo", None, _ten_px_per_character) == ["one", "two"]

    def test_a_long_line_is_left_alone_without_a_width(self) -> None:
        """An auto-sizing label has nothing to wrap against."""
        long = "a" * 500
        assert wrap_text(long, None, _ten_px_per_character) == [long]

    def test_newlines_split_even_when_the_whole_text_would_fit(self) -> None:
        assert wrap_text("a\nb", 1000, _ten_px_per_character) == ["a", "b"]

    def test_a_blank_line_is_kept(self) -> None:
        """A gap between paragraphs is content, not whitespace to tidy."""
        assert wrap_text("a\n\nb", 1000, _ten_px_per_character) == ["a", "", "b"]

    def test_the_empty_string_is_one_empty_line(self) -> None:
        """Not zero lines: the count is the height, and a label has one."""
        assert wrap_text("", None, _ten_px_per_character) == [""]
        assert wrap_text("", 100, _ten_px_per_character) == [""]

    @pytest.mark.parametrize("newline", ["\r\n", "\r"])
    def test_carriage_returns_are_normalised(self, newline: str) -> None:
        """A file read in text mode on one platform and binary on another
        otherwise wraps differently and leaves a stray glyph per line."""
        assert wrap_text(f"one{newline}two", None, _ten_px_per_character) == [
            "one",
            "two",
        ]


class TestGreedyWrapping:
    """Words move to the next line when the current one is full."""

    def test_text_that_fits_stays_on_one_line(self) -> None:
        assert wrap_text("ab cd", 100, _ten_px_per_character) == ["ab cd"]

    def test_text_that_does_not_fit_breaks_at_a_space(self) -> None:
        # "ab cd" is 50px; at 40px the second word moves down.
        assert wrap_text("ab cd", 40, _ten_px_per_character) == ["ab", "cd"]

    def test_a_line_is_filled_before_the_next_is_started(self) -> None:
        """Greedy, not balanced: the first line takes all it can hold."""
        assert wrap_text("a b c d e", 50, _ten_px_per_character) == ["a b c", "d e"]

    def test_every_line_fits_the_width(self) -> None:
        text = "the guara falcon circles the cerrado at dusk"
        for line in wrap_text(text, 120, _ten_px_per_character):
            assert _ten_px_per_character(line) <= 120

    def test_a_run_of_spaces_is_preserved(self) -> None:
        """`str.split()` would collapse it; "10  20" is an alignment."""
        assert wrap_text("10  20", 1000, _ten_px_per_character) == ["10  20"]

    def test_wrapping_loses_no_words(self) -> None:
        text = "alpha beta gamma delta epsilon zeta eta theta"
        lines = wrap_text(text, 100, _ten_px_per_character)
        assert " ".join(lines).split() == text.split()


class TestWordsLongerThanTheLine:
    """The case that has no good answer, only a chosen one."""

    def test_an_oversized_word_is_broken_rather_than_overflowing(self) -> None:
        assert wrap_text("abcdefgh", 30, _ten_px_per_character) == [
            "abc",
            "def",
            "gh",
        ]

    def test_an_oversized_word_starts_on_a_fresh_line(self) -> None:
        """The text before it is not dragged into the break."""
        lines = wrap_text("hi abcdefgh", 30, _ten_px_per_character)
        assert lines[0] == "hi"

    def test_splitting_returns_the_whole_word_when_it_fits(self) -> None:
        assert split_oversized_word("abc", 100, _ten_px_per_character) == ("abc", "")

    def test_splitting_keeps_at_least_one_character(self) -> None:
        """A width narrower than one glyph is a layout mistake.

        Returning an empty head for it would make the caller loop
        forever, which hides the mistake instead of showing it.
        """
        assert split_oversized_word("abc", 1, _ten_px_per_character) == ("a", "bc")

    def test_a_width_narrower_than_a_glyph_still_terminates(self) -> None:
        assert wrap_text("abc", 1, _ten_px_per_character) == ["a", "b", "c"]

    def test_a_zero_width_still_terminates(self) -> None:
        assert wrap_text("ab", 0, _ten_px_per_character) == ["a", "b"]


class TestAMeasurerThatKnowsNothing:
    """The headless renderer answers 0 to every measurement.

    It draws nothing, so it has nothing to measure with -- and wrapping
    must not hang or produce nonsense when every candidate "fits".
    """

    @staticmethod
    def _always_zero(text: str) -> int:
        return 0

    def test_everything_fits_so_nothing_wraps(self) -> None:
        assert wrap_text("a b c d", 10, self._always_zero) == ["a b c d"]

    def test_explicit_newlines_still_split(self) -> None:
        assert wrap_text("a\nb", 10, self._always_zero) == ["a", "b"]


class TestPlacingACaretFromAPixelOffset:
    """A caret sits between characters, so the answer is a boundary."""

    @pytest.mark.parametrize(
        "offset,expected",
        [
            (-50, 0),
            (0, 0),
            (4, 0),
            (6, 1),
            (14, 1),
            (16, 2),
            (1000, 6),
        ],
    )
    def test_the_nearest_boundary_wins(self, offset: int, expected: int) -> None:
        """Left half of a glyph puts the caret before it, right half after.

        That is what every text field does, and it is what makes a click
        at the end of a word land after the word rather than inside it.
        """
        assert caret_index_at("abcdef", offset, _ten_px_per_character) == expected

    def test_exactly_on_a_midpoint_rounds_forwards(self) -> None:
        """Arbitrary, but it has to be one or the other, and a click
        landing on the same pixel twice must give the same answer."""
        assert caret_index_at("abcdef", 25, _ten_px_per_character) == 3

    def test_an_offset_past_the_text_clamps_to_the_end(self) -> None:
        """A drag that leaves the widget is an ordinary thing to do."""
        assert caret_index_at("abc", 9999, _ten_px_per_character) == 3

    def test_empty_text_has_only_one_position(self) -> None:
        assert caret_index_at("", 500, _ten_px_per_character) == 0

    def test_a_measurer_that_knows_nothing_lands_at_the_end(self) -> None:
        """The headless renderer measures everything as 0 wide.

        Every prefix is then 0 px, the offset is past all of them, and
        the caret goes to the end -- the same place `TextInput` puts it
        when it has not been drawn yet and so has nothing to measure
        with. Consistent, and the only answer available.
        """
        assert caret_index_at("abc", 50, lambda _text: 0) == 3
