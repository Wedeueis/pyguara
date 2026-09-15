"""Container background component."""

from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget


class Panel(Widget):
    """A colored rectangle container."""

    def __init__(
        self,
        position: Vector2,
        size: Vector2,
        color: Color | None = None,
        border_width: int = 1,
    ) -> None:
        """Initialize the panel."""
        super().__init__(position, size)
        self._color = color
        self.border_width = border_width

    def render(self, renderer: UIRenderer) -> None:
        """Render the panel background and border."""
        # A panel is a card sitting on the canvas, not the canvas itself --
        # `surface_card` is what separates it from the background behind it.
        bg_color = self._color or self.theme.colors.surface_card
        renderer.draw_rect(self.rect, bg_color, width=0)

        renderer.draw_rect(self.rect, self.theme.colors.edge, width=self.border_width)
