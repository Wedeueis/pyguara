"""Progress indicator."""

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget


class ProgressBar(Widget):
    """Visualizes progress 0.0 to 1.0."""

    def __init__(
        self,
        position: Vector2,
        size: Vector2 = Vector2(200, 20),
        value: float = 0.5,
        fill_color: Color | None = None,
        bg_color: Color | None = None,
    ) -> None:
        """Initialize the progress bar.

        `fill_color`/`bg_color` default to the active theme, resolved at
        render time so a later `set_theme()` is honoured.
        """
        super().__init__(position, size)
        self.value = max(0.0, min(1.0, value))
        self.fill_color = fill_color
        self.bg_color = bg_color

    def set_value(self, value: float) -> None:
        """Update the progress value (clamped 0.0-1.0)."""
        self.value = max(0.0, min(1.0, value))

    def render(self, renderer: UIRenderer) -> None:
        """Render the progress bar."""
        # Background
        renderer.draw_rect(self.rect, self.bg_color or self.theme.colors.background)

        # Border
        renderer.draw_rect(self.rect, self.theme.colors.border, width=1)

        # Fill
        if self.value > 0:
            fill_width = int(self.rect.width * self.value)
            fill_rect = Rect(self.rect.x, self.rect.y, fill_width, self.rect.height)
            renderer.draw_rect(
                fill_rect, self.fill_color or self.theme.colors.secondary
            )
