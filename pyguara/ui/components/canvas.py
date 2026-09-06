"""Custom drawing surface."""

from pyguara.common.types import Color, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget


class Canvas(Widget):
    """A generic container for custom drawing.

    Useful for mini-maps, model previews, or custom graphs.
    """

    def __init__(
        self, position: Vector2, size: Vector2, bg_color: Color | None = None
    ) -> None:
        """Initialize the canvas."""
        super().__init__(position, size)
        self.bg_color = bg_color or self.theme.colors.background

    def render(self, renderer: UIRenderer) -> None:
        """Render the background and children."""
        # Draw background / Clear
        renderer.draw_rect(self.rect, self.bg_color)

        # The 'custom drawing' is usually done by attaching children
        # or overriding render() in a subclass of Canvas.
        pass
