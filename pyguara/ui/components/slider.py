"""Value slider component."""

from pyguara.common.types import Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget
from pyguara.ui.types import UIElementState, UIEventType


class Slider(Widget):
    """Draggable value selector."""

    def __init__(
        self,
        position: Vector2,
        width: int = 150,
        min_val: float = 0.0,
        max_val: float = 1.0,
        step: float = 0.0,
    ) -> None:
        """Initialize the slider."""
        super().__init__(position, Vector2(width, 20))
        self.min_val = min_val
        self.max_val = max_val
        self.value = min_val
        self.step = step
        self._dragging = False

    def render(self, renderer: UIRenderer) -> None:
        """Render the slider track and handle."""
        # 1. Track Line
        mid_y = self.rect.y + self.rect.height // 2
        renderer.draw_line(
            Vector2(self.rect.x, mid_y),
            Vector2(self.rect.x + self.rect.width, mid_y),
            self.theme.colors.border,
            width=2,
        )

        # 2. Handle (Knob)
        # Calculate position 0..1
        ratio = (
            (self.value - self.min_val) / (self.max_val - self.min_val)
            if self.max_val > self.min_val
            else 0
        )
        handle_x = self.rect.x + int(ratio * self.rect.width)

        handle_color = self.theme.colors.secondary
        if self.state == UIElementState.HOVERED or self._dragging:
            handle_color = self.theme.colors.primary

        renderer.draw_circle(Vector2(handle_x, mid_y), 8, handle_color)

    def _process_input(
        self, event_type: UIEventType, position: Vector2, button: int
    ) -> bool:
        if event_type == UIEventType.MOUSE_DOWN:
            if (
                self.rect.x <= position.x <= self.rect.x + self.rect.width
                and self.rect.y <= position.y <= self.rect.y + self.rect.height
            ):
                self._dragging = True
                self._update_value_from_pos(position.x)
                return True

        elif event_type == UIEventType.MOUSE_UP:
            self._dragging = False

        elif event_type == UIEventType.MOUSE_MOVE:
            if self._dragging:
                self._update_value_from_pos(position.x)
                return True

        return super()._process_input(event_type, position, button)

    def _update_value_from_pos(self, x: float) -> None:
        relative_x = x - self.rect.x
        ratio = max(0.0, min(1.0, relative_x / self.rect.width))
        new_val = self.min_val + ratio * (self.max_val - self.min_val)

        if self.step > 0:
            new_val = round(new_val / self.step) * self.step

        self.value = new_val
