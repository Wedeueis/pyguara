"""Interactive button component."""

from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget
from pyguara.ui.types import UIElementState


class Button(Widget):
    """Clickable button with state styling."""

    def __init__(
        self, text: str, position: Vector2, size: Vector2 = Vector2(120, 40)
    ) -> None:
        """Initialize the button."""
        super().__init__(position, size)
        self.focusable = True
        self.text = text
        self.text_padding = 5

    def fill_color(self) -> Color:
        """The background for the current state.

        Reads the action roles rather than `primary`/`secondary`, so hover
        and press are colours a theme chose for exactly those states
        instead of the accent doing double duty.

        Returns:
            The fill colour.
        """
        colors = self.theme.colors
        if self.state == UIElementState.DISABLED:
            return colors.action_disabled
        if self.state == UIElementState.PRESSED:
            return colors.action_primary_press
        if self.state == UIElementState.HOVERED:
            return colors.action_primary_hover
        return colors.action_primary

    def text_color(self) -> Color:
        """The label colour for the current state.

        Returns:
            The text colour that stays legible on `fill_color()`.
        """
        colors = self.theme.colors
        if self.state == UIElementState.DISABLED:
            return colors.text_on_disabled
        return colors.text_on_primary

    def border_color(self) -> Color:
        """The edge colour, which doubles as the focus indicator.

        Returns:
            The focus ring when focused, the strong edge otherwise.
        """
        colors = self.theme.colors
        if self.state == UIElementState.FOCUSED:
            return colors.focus_ring
        return colors.edge_strong

    def render(self, renderer: UIRenderer) -> None:
        """Render the button in its current state."""
        renderer.draw_rect(self.rect, self.fill_color(), width=0)
        renderer.draw_rect(
            self.rect, self.border_color(), width=self.theme.borders.width
        )
        self.render_label(renderer)

    def render_label(self, renderer: UIRenderer) -> None:
        """Draw the centred label.

        Split from `render()` so a subclass can put something between the
        fill and the text -- a bevel, for instance -- without repeating the
        centring maths.

        Args:
            renderer: The UI renderer to draw through.
        """
        size = self.theme.fonts.size_normal
        w, h = renderer.get_text_size(self.text, size)

        text_x = self.rect.x + (self.rect.width - w) // 2
        text_y = self.rect.y + (self.rect.height - h) // 2

        renderer.draw_text(self.text, Vector2(text_x, text_y), self.text_color())
