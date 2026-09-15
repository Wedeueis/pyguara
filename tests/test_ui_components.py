from typing import Any
from unittest.mock import MagicMock

import pytest

from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.button import Button
from pyguara.ui.components.panel import Panel
from pyguara.ui.components.text import Label
from pyguara.ui.components.text_input import TextInput
from pyguara.ui.theme import UITheme, set_theme
from pyguara.ui.types import ColorScheme, UIElementState, UIEventType


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
