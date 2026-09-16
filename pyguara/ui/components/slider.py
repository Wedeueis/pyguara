"""Value slider component."""

from collections.abc import Callable

from pyguara.common.types import Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget
from pyguara.ui.types import UIElementState, UIEventType


class Slider(Widget):
    """Draggable value selector."""

    VALUE_GAP = 8
    """Pixels between the track and its printed value."""

    def __init__(
        self,
        position: Vector2,
        width: int = 150,
        min_val: float = 0.0,
        max_val: float = 1.0,
        step: float = 0.0,
        *,
        show_value: bool = False,
    ) -> None:
        """Initialize the slider.

        Raises:
            ValueError: If `max_val` is not greater than `min_val`, or
                `width` is not positive -- both leave the slider with no
                usable range and would divide by zero on interaction.
        """
        if max_val <= min_val:
            raise ValueError(
                f"Slider max_val ({max_val}) must be greater than min_val ({min_val})"
            )
        if width <= 0:
            raise ValueError(f"Slider width must be positive, got {width}")
        super().__init__(position, Vector2(width, 20))
        self.focusable = True
        self.min_val = min_val
        self.max_val = max_val
        self.value = min_val
        self.step = step
        self.show_value = show_value
        self._dragging = False

        # Fired only when the value actually moves. Without it an options
        # menu has to poll every slider every frame to notice a drag.
        self.on_change: Callable[[float], None] | None = None

    @property
    def ratio(self) -> float:
        """Where the handle sits, 0.0 at `min_val` and 1.0 at `max_val`."""
        span = self.max_val - self.min_val
        return (self.value - self.min_val) / span if span > 0 else 0.0

    def set_value(self, value: float) -> None:
        """Move the handle, firing `on_change` if this is a real change.

        Args:
            value: The new value, clamped to the slider's range.
        """
        clamped = max(self.min_val, min(self.max_val, value))
        if clamped == self.value:
            return
        self.value = clamped
        if self.on_change is not None:
            self.on_change(clamped)

    def render(self, renderer: UIRenderer) -> None:
        """Render the slider track and handle."""
        colors = self.theme.colors
        track_width = self.rect.width - (self._value_width(renderer))

        # 1. Track Line
        mid_y = self.rect.y + self.rect.height // 2
        renderer.draw_line(
            Vector2(self.rect.x, mid_y),
            Vector2(self.rect.x + track_width, mid_y),
            colors.edge_strong,
            width=2,
        )

        # 2. Handle (Knob)
        handle_x = self.rect.x + int(self.ratio * track_width)

        handle_color = colors.action_secondary
        if self.state == UIElementState.HOVERED or self._dragging:
            handle_color = colors.action_primary_hover
        elif self.state == UIElementState.FOCUSED and self.focus_visible:
            handle_color = colors.focus_ring

        renderer.draw_circle(Vector2(handle_x, mid_y), 8, handle_color)

        # 3. The number, when asked for. An audio slider without one is a
        # guess, which is why every options screen prints it.
        if self.show_value:
            renderer.draw_text(
                self._value_text(),
                Vector2(self.rect.x + track_width + self.VALUE_GAP, self.rect.y),
                colors.text_body,
                self.theme.fonts.size_small,
            )

    def _value_text(self) -> str:
        """The value as the options screens print it."""
        return f"{self.value:.2f}"

    def _value_width(self, renderer: UIRenderer) -> int:
        """Pixels reserved at the right for the value readout."""
        if not self.show_value:
            return 0
        width, _ = renderer.get_text_size(
            self._value_text(), self.theme.fonts.size_small
        )
        return width + self.VALUE_GAP

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

        self.set_value(new_val)
