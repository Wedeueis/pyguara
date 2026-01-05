"""Progress indicator."""

from pyguara.common.types import Vector2, Rect
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget


class ProgressBar(Widget):
    """Visualizes progress 0.0 to 1.0."""

    def __init__(
        self, position: Vector2, size: Vector2 = Vector2(200, 20), value: float = 0.5
    ) -> None:
        """Initialize the progress bar."""
        super().__init__(position, size)
        self.value = max(0.0, min(1.0, value))
        self.fill_color = self.theme.colors.secondary
        self.bg_color = self.theme.colors.background

    def set_value(self, value: float) -> None:
        """Update the progress value (clamped 0.0-1.0)."""
        self.value = max(0.0, min(1.0, value))

    def render(self, renderer: UIRenderer) -> None:
        """Render the progress bar."""
        # Background
        renderer.draw_rect(self.rect, self.bg_color)

        # Border
        renderer.draw_rect(self.rect, self.theme.colors.border, width=1)

        # Fill
        if self.value > 0:
            fill_width = int(self.rect.width * self.value)
            fill_rect = Rect(self.rect.x, self.rect.y, fill_width, self.rect.height)
            renderer.draw_rect(fill_rect, self.fill_color)
