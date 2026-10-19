from typing import Any
from unittest.mock import MagicMock

import pytest

from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.button import Button
from pyguara.ui.components.canvas import Canvas
from pyguara.ui.components.panel import Panel
from pyguara.ui.components.text import Label
from pyguara.ui.components.text_input import TextInput
from pyguara.ui.theme import UITheme, set_theme
from pyguara.ui.types import ColorScheme, TextAlign, UIElementState, UIEventType


@pytest.fixture  # type: ignore[misc]
def mock_renderer() -> Any:
    r = MagicMock(spec=UIRenderer)
    # Mock get_text_size to return something valid
    r.get_text_size.return_value = (50, 20)
    return r


def test_label_rendering(mock_renderer: Any) -> None:
    """Test that label measures text and draws it."""
    lbl = Label("Hello", Vector2(10, 10), font_size=12, color=Color(255, 0, 0))

    # Render
    lbl.render(mock_renderer)

    # 1. Should have measured text
    mock_renderer.get_text_size.assert_called_with("Hello", 12)

    # 2. Should have updated rect based on measurement
    assert lbl.rect.width == 50
    assert lbl.rect.height == 20

    # 3. Should have drawn text
    mock_renderer.draw_text.assert_called()
    call_args = mock_renderer.draw_text.call_args
    # Check args: text, position, color, size
    assert call_args[0][0] == "Hello"
    # Position (10, 10)
    pos = call_args[0][1]
    assert pos.x == 10 and pos.y == 10
    # Color
    assert call_args[0][2] == Color(255, 0, 0)
    # Font Size
    assert call_args[0][3] == 12


def test_button_rendering(mock_renderer: Any) -> None:
    """Test button rendering in different states."""
    btn = Button("Click Me", Vector2(100, 100), size=Vector2(100, 40))

    # Render Normal
    btn.render(mock_renderer)

    # Should draw background, border, text
    assert mock_renderer.draw_rect.call_count == 2  # BG + Border
    mock_renderer.draw_text.assert_called_once()

    # Render Hovered
    btn.state = UIElementState.HOVERED
    mock_renderer.reset_mock()
    btn.render(mock_renderer)
    assert mock_renderer.draw_rect.call_count == 2


def test_button_interaction() -> None:
    """Test input handling on a button."""
    btn = Button("Click", Vector2(10, 10), Vector2(50, 20))
    # Rect is x=10, y=10, w=50, h=20. Ends at 60, 30.

    # 1. Mouse Move OUTSIDE
    processed = btn.handle_event(UIEventType.MOUSE_MOVE, Vector2(100, 100))
    assert not processed
    # Note: State may vary based on previous state

    # 2. Mouse Move INSIDE
    processed = btn.handle_event(UIEventType.MOUSE_MOVE, Vector2(20, 20))
    assert processed
    assert btn.state == UIElementState.HOVERED

    # 3. Mouse Down INSIDE
    processed = btn.handle_event(UIEventType.MOUSE_DOWN, Vector2(20, 20), button=1)
    assert processed
    assert btn.state == UIElementState.PRESSED  # type: ignore[comparison-overlap]

    # 4. Mouse Up INSIDE (Click)
    mock_click = MagicMock()  # type: ignore[unreachable]
    btn.on_click = mock_click

    processed = btn.handle_event(UIEventType.MOUSE_UP, Vector2(20, 20))
    assert processed
    assert btn.state == UIElementState.HOVERED
    mock_click.assert_called_once_with(btn)

    # 5. Mouse Down then Out then Up (Cancel)
    btn.state = UIElementState.PRESSED
    processed = btn.handle_event(UIEventType.MOUSE_UP, Vector2(100, 100))
    # Should return True as we consumed the "release" even if canceled?
    # Logic: if self.state == PRESSED: if contains... else state=NORMAL; return True
    assert processed
    assert btn.state == UIElementState.NORMAL
    # Click callback NOT called again
    assert mock_click.call_count == 1


def test_widget_state_colors() -> None:
    """Test the get_state_color logic in Widget base."""
    # We can use Button as it inherits Widget
    btn = Button("Test", Vector2(0, 0))
    base_color = Color(100, 100, 100, 255)

    # Normal
    btn.state = UIElementState.NORMAL
    assert btn.get_state_color(base_color) == base_color

    # Disabled
    btn.state = UIElementState.DISABLED
    dim_color = btn.get_state_color(base_color)
    assert dim_color.r == 50
    assert dim_color.g == 50
    assert dim_color.b == 50
    assert dim_color.a == 255


class TestComponentsReadTheSemanticRoles:
    """Components used to overload the base five colours.

    `secondary` meant the accent, the hover fill, the focus ring and a
    checkbox tick all at once, and a placeholder was drawn in the *border*
    colour because it happened to be dim. Each of those is now a role a
    theme states outright, which is what lets a design system re-skin the
    stock components without touching them.
    """

    def test_a_button_fills_with_the_action_states(self, mock_renderer: Any) -> None:
        theme = UITheme(
            name="t",
            colors=ColorScheme.derive(
                action_primary=Color(1, 1, 1),
                action_primary_hover=Color(2, 2, 2),
                action_primary_press=Color(3, 3, 3),
                action_disabled=Color(4, 4, 4),
            ),
        )
        set_theme(theme)
        try:
            btn = Button("Go", Vector2(0, 0))
            seen = {}
            for state in (
                UIElementState.NORMAL,
                UIElementState.HOVERED,
                UIElementState.PRESSED,
                UIElementState.DISABLED,
            ):
                btn.state = state
                seen[state] = btn.fill_color()

            assert seen[UIElementState.NORMAL] == Color(1, 1, 1)
            assert seen[UIElementState.HOVERED] == Color(2, 2, 2)
            assert seen[UIElementState.PRESSED] == Color(3, 3, 3)
            assert seen[UIElementState.DISABLED] == Color(4, 4, 4)
        finally:
            set_theme(UITheme())

    def test_a_focused_button_borders_with_the_focus_ring(self) -> None:
        set_theme(
            UITheme(name="t", colors=ColorScheme.derive(focus_ring=Color(9, 9, 9)))
        )
        try:
            btn = Button("Go", Vector2(0, 0))
            btn.state = UIElementState.FOCUSED
            btn.focus_visible = True

            assert btn.border_color() == Color(9, 9, 9)
        finally:
            set_theme(UITheme())

    def test_a_placeholder_is_faint_text_not_a_border(self, mock_renderer: Any) -> None:
        set_theme(
            UITheme(
                name="t",
                colors=ColorScheme.derive(
                    text_faint=Color(7, 7, 7), border=Color(8, 8, 8)
                ),
            )
        )
        try:
            field = TextInput(Vector2(0, 0), placeholder="name")

            field.render(mock_renderer)

            assert mock_renderer.draw_text.call_args.args[2] == Color(7, 7, 7)
        finally:
            set_theme(UITheme())

    def test_a_panel_is_a_card_not_the_canvas(self, mock_renderer: Any) -> None:
        """A panel drawn in the background colour is invisible on it."""
        set_theme(
            UITheme(
                name="t",
                colors=ColorScheme.derive(
                    background=Color(5, 5, 5), surface_card=Color(6, 6, 6)
                ),
            )
        )
        try:
            panel = Panel(Vector2(0, 0), Vector2(10, 10))

            panel.render(mock_renderer)

            assert mock_renderer.draw_rect.call_args_list[0].args[1] == Color(6, 6, 6)
        finally:
            set_theme(UITheme())


class TestContainersDrawTheirChildren:
    """`Panel` and `Canvas` laid their children out and then never drew them.

    A panel with contents rendered as an empty box, so anything built that
    way had to add its contents as separate roots beside the panel and keep
    the two in sync by hand. `BoxContainer` always drew its children; these
    two were the odd ones out, and `Canvas`'s docstring even claimed it.
    """

    def test_a_panel_draws_a_child(self, mock_renderer: Any) -> None:
        panel = Panel(Vector2(0, 0), Vector2(100, 50))
        panel.add_child(Label("inside", Vector2(10, 10)))

        panel.render(mock_renderer)

        assert mock_renderer.draw_text.call_args.args[0] == "inside"

    def test_a_panel_skips_a_hidden_child(self, mock_renderer: Any) -> None:
        panel = Panel(Vector2(0, 0), Vector2(100, 50))
        hidden = Label("inside", Vector2(10, 10))
        hidden.visible = False
        panel.add_child(hidden)

        panel.render(mock_renderer)

        mock_renderer.draw_text.assert_not_called()

    def test_a_canvas_draws_a_child(self, mock_renderer: Any) -> None:
        canvas = Canvas(Vector2(0, 0), Vector2(100, 50))
        canvas.add_child(Label("inside", Vector2(10, 10)))

        canvas.render(mock_renderer)

        assert mock_renderer.draw_text.call_args.args[0] == "inside"


class TestLabelAlignment:
    """A caller centring text used to guess its width by eye.

    `Label` measures its own text at render time already -- `width` +
    `align` puts that measurement to use instead of a hardcoded x offset
    that is wrong the moment the text, the font or the panel changes.
    """

    def test_without_a_width_the_rect_is_exactly_the_text(
        self, mock_renderer: Any
    ) -> None:
        """Unchanged behaviour for every caller that does not opt in."""
        mock_renderer.get_text_size.return_value = (64, 20)
        label = Label("Hi", Vector2(10, 10))

        label.render(mock_renderer)

        assert label.rect.width == 64
        assert mock_renderer.draw_text.call_args.args[1].x == 10

    def test_center_places_the_text_in_the_middle_of_the_width(
        self, mock_renderer: Any
    ) -> None:
        mock_renderer.get_text_size.return_value = (60, 20)
        label = Label("Hi", Vector2(100, 10), width=200, align=TextAlign.CENTER)

        label.render(mock_renderer)

        # (200 - 60) // 2 == 70, offset from the label's own x (100).
        assert mock_renderer.draw_text.call_args.args[1].x == 170

    def test_right_aligns_to_the_far_edge(self, mock_renderer: Any) -> None:
        mock_renderer.get_text_size.return_value = (60, 20)
        label = Label("Hi", Vector2(100, 10), width=200, align=TextAlign.RIGHT)

        label.render(mock_renderer)

        assert mock_renderer.draw_text.call_args.args[1].x == 240

    def test_a_fixed_width_does_not_shrink_to_the_text(
        self, mock_renderer: Any
    ) -> None:
        mock_renderer.get_text_size.return_value = (10, 20)
        label = Label("Hi", Vector2(0, 0), width=200)

        label.render(mock_renderer)

        assert label.rect.width == 200

    def test_height_is_still_measured_with_a_fixed_width(
        self, mock_renderer: Any
    ) -> None:
        mock_renderer.get_text_size.return_value = (10, 33)
        label = Label("Hi", Vector2(0, 0), width=200)

        label.render(mock_renderer)

        assert label.rect.height == 33


class _MeasuringRenderer:
    """A `UIRenderer` whose text metrics are arithmetic, not a font.

    At the default size 16: 10 px per character and a 20 px line, so
    every expectation below is a number a reader can check rather than a
    number Arial produced. Both scale with the requested size, so a test
    can change `font_size` and see the layout respond.
    """

    LINE_HEIGHT = 20

    def __init__(self) -> None:
        self.texts: list[tuple[str, float, float]] = []
        self.measurements = 0

    def get_text_size(self, text: str, size: int) -> tuple[int, int]:
        self.measurements += 1
        return (len(text) * 10 * size // 16, self.LINE_HEIGHT * size // 16)

    def draw_text(
        self, text: str, position: Vector2, color: Color, size: int = 16
    ) -> None:
        self.texts.append((text, position.x, position.y))

    def __getattr__(self, name: str) -> Any:
        return MagicMock()


class TestALabelWrapsToItsWidth:
    """Text longer than the label used to run straight out of it.

    `Label` made exactly one `draw_text` call however long the string
    was, so a 150 px label drew 423 px of text -- 273 px of overflow,
    over whatever sat beside it.
    """

    SENTENCE = "the guara falcon circles the cerrado"

    def test_a_long_line_becomes_several(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label(self.SENTENCE, Vector2(0, 0), width=120)

        label.render(renderer)

        assert len(label.lines) > 1
        assert len(renderer.texts) == len(label.lines)

    def test_no_line_exceeds_the_width(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label(self.SENTENCE, Vector2(0, 0), width=120)

        label.render(renderer)

        for line in label.lines:
            assert len(line) * 10 <= 120

    def test_the_height_grows_with_the_line_count(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label(self.SENTENCE, Vector2(0, 0), width=120)

        label.render(renderer)

        assert label.rect.height == 20 * len(label.lines)

    def test_the_lines_are_stacked_one_line_height_apart(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label(self.SENTENCE, Vector2(7, 13), width=120)

        label.render(renderer)

        ys = [y for _, _, y in renderer.texts]
        assert ys == [13 + 20 * i for i in range(len(ys))]

    def test_no_word_is_lost(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label(self.SENTENCE, Vector2(0, 0), width=120)

        label.render(renderer)

        assert " ".join(label.lines).split() == self.SENTENCE.split()

    def test_a_short_label_is_unchanged(self) -> None:
        """One line, one draw call, the height it always had."""
        renderer = _MeasuringRenderer()
        label = Label("Hi", Vector2(5, 5), width=200)

        label.render(renderer)

        assert label.lines == ["Hi"]
        assert renderer.texts == [("Hi", 5, 5)]
        assert label.rect.height == 20


class TestALabelHonoursExplicitNewlines:
    """Measure and draw disagreed about `\\n`, so layout was wrong.

    `get_text_size` is `pygame.font.Font.size`, which measures one line
    and ignores newlines; `draw_text` is `Font.render`, which honours
    them. "first line\\nsecond line" measured 146x18 and drew 79x38 -- the
    width too wide by 67 px and the height exactly half, so a container
    stacking siblings from the measured height put the next widget on top
    of the second line.
    """

    def test_an_auto_sized_label_still_splits_on_a_newline(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label("one\nthree", Vector2(0, 0))

        label.render(renderer)

        assert label.lines == ["one", "three"]
        assert len(renderer.texts) == 2

    def test_its_width_is_the_widest_line_not_the_whole_string(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label("one\nthree", Vector2(0, 0))

        label.render(renderer)

        # "three" is 5 characters; the un-split string would measure 9.
        assert label.rect.width == 50

    def test_its_height_counts_every_line(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label("one\nthree", Vector2(0, 0))

        label.render(renderer)

        assert label.rect.height == 40

    def test_a_blank_line_takes_its_height_without_being_drawn(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label("a\n\nb", Vector2(0, 0))

        label.render(renderer)

        assert label.lines == ["a", "", "b"]
        assert label.rect.height == 60
        assert [text for text, _, _ in renderer.texts] == ["a", "b"]
        # And "b" is on the third line, not the second.
        assert renderer.texts[1][2] == 40


class TestAlignmentIsPerLine:
    """A centred paragraph should look centred, not like a centred block."""

    def test_each_line_is_centred_on_its_own_width(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label("aaaa\nbb", Vector2(0, 0), width=200, align=TextAlign.CENTER)

        label.render(renderer)

        xs = [x for _, x, _ in renderer.texts]
        assert xs == [(200 - 40) // 2, (200 - 20) // 2]
        assert xs[0] != xs[1]

    def test_each_line_is_right_aligned_on_its_own_width(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label("aaaa\nbb", Vector2(0, 0), width=200, align=TextAlign.RIGHT)

        label.render(renderer)

        xs = [x for _, x, _ in renderer.texts]
        assert xs == [200 - 40, 200 - 20]


class TestTheWrapIsCached:
    """`render` measures every frame; wrapping costs a measurement a word.

    A static HUD label must re-wrap once, not sixty times a second.
    """

    def test_a_second_render_does_not_re_wrap(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label("the guara falcon circles", Vector2(0, 0), width=120)

        label.render(renderer)
        after_first = renderer.measurements
        label.render(renderer)
        after_second = renderer.measurements

        # The second pass still measures the line height and each line,
        # but not every candidate considered while breaking the text.
        assert after_second - after_first < after_first

    def test_changing_the_text_re_wraps(self) -> None:
        renderer = _MeasuringRenderer()
        label = Label("short", Vector2(0, 0), width=120)
        label.render(renderer)

        label.set_text("the guara falcon circles the cerrado")
        label.render(renderer)

        assert len(label.lines) > 1

    def test_changing_the_font_size_re_wraps(self) -> None:
        """Bigger glyphs mean fewer words per line, cache or no cache."""
        renderer = _MeasuringRenderer()
        label = Label("aa bb cc dd", Vector2(0, 0), width=80)
        label.render(renderer)
        at_sixteen = len(label.lines)

        label.font_size = 32
        label.render(renderer)

        assert len(label.lines) > at_sixteen

    def test_a_resized_label_re_wraps(self) -> None:
        """A container that widens the label must get wider lines."""
        renderer = _MeasuringRenderer()
        label = Label("aaaa bbbb cccc", Vector2(0, 0), width=50)
        label.render(renderer)
        narrow = len(label.lines)

        label.rect.width = 200
        label.render(renderer)

        assert len(label.lines) < narrow


class _VariableHeightRenderer(_MeasuringRenderer):
    """A measurer whose reported height depends on the string.

    No shipped backend does this -- both answer `pygame.font.Font.size`,
    whose height is constant at a given size -- but `UIRenderer` promises
    nothing about it, and a FreeType-backed measurer would return the ink
    extent. A label whose lines advanced by different amounts depending
    on their accents is a bug nobody would think to look for, so the
    uniform step is a contract rather than an accident of the backend.
    """

    def get_text_size(self, text: str, size: int) -> tuple[int, int]:
        width, height = super().get_text_size(text, size)
        return (width, height + 10 * sum(1 for c in text if c.isupper()))


class TestTheLineStepIsAPropertyOfTheFont:
    """Not of the line, so lines are evenly spaced whatever they contain."""

    def test_lines_are_evenly_spaced_regardless_of_content(self) -> None:
        renderer = _VariableHeightRenderer()
        label = Label("AAA\naaa\nAAA", Vector2(0, 0))

        label.render(renderer)

        ys = [y for _, _, y in renderer.texts]
        steps = {b - a for a, b in zip(ys, ys[1:], strict=False)}
        assert steps == {_MeasuringRenderer.LINE_HEIGHT}

    def test_the_height_does_not_inflate_with_the_content(self) -> None:
        renderer = _VariableHeightRenderer()
        label = Label("ABCDEF", Vector2(0, 0))

        label.render(renderer)

        assert label.rect.height == _MeasuringRenderer.LINE_HEIGHT
