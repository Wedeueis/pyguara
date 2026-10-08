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
        # A card lifts off the canvas, so it is one of the two stock
        # widgets that casts a shadow; the inset ones (text field, progress
        # track, checkbox box) are recessed and must not.
        self.draw_shadow(renderer)
        radius = self.theme.borders.radius
        renderer.draw_rect(self.rect, bg_color, width=0, border_radius=radius)

        renderer.draw_rect(
            self.rect,
            self.theme.colors.edge,
            width=self.border_width,
            border_radius=radius,
        )

        # Children, which a panel used to lay out and then never draw --
        # so a panel with contents rendered as an empty box unless the
        # caller added the contents as a separate root beside it.
        for child in self.children:
            if child.visible:
                child.render(renderer)
