"""Navigation bar component."""

from pyguara.common.types import Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.layout import BoxContainer
from pyguara.ui.types import LayoutDirection, LayoutAlignment
from pyguara.ui.components.panel import Panel


class NavBar(BoxContainer):
    """Horizontal bar typically at the top of a screen.

    Combines a Panel background with a horizontal layout.
    """

    def __init__(self, width: int, height: int = 50) -> None:
        """Initialize the navbar."""
        super().__init__(
            position=Vector2(0, 0),
            size=Vector2(width, height),
            direction=LayoutDirection.HORIZONTAL,
            alignment=LayoutAlignment.START,
            spacing=10,
        )
        # Add background panel manually since BoxContainer doesn't render itself
        self.background = Panel(
            Vector2(0, 0), Vector2(width, height), color=self.theme.colors.background
        )

    def render(self, renderer: UIRenderer) -> None:
        """Render the background and then children."""
        self.background.render(renderer)
        super().render(renderer)
