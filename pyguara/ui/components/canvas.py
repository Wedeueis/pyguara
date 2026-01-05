"""Custom drawing surface."""

from typing import Optional
from pyguara.common.types import Vector2, Color
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget


class Canvas(Widget):
    """A generic container for custom drawing.

    Useful for mini-maps, model previews, or custom graphs.
    """

    def __init__(
        self, position: Vector2, size: Vector2, bg_color: Optional[Color] = None
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
