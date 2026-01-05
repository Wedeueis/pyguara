"""Layout containers."""

from pyguara.common.types import Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.base import UIElement
from pyguara.ui.types import LayoutDirection, LayoutAlignment


class BoxContainer(UIElement):
    """Stacks children linearly with alignment support."""

    def __init__(
        self,
        position: Vector2,
        size: Vector2,
        direction: LayoutDirection = LayoutDirection.VERTICAL,
        alignment: LayoutAlignment = LayoutAlignment.START,
        spacing: int = 5,
    ) -> None:
        """Initialize the layout container."""
        super().__init__(position, size)
        self.direction = direction
        self.alignment = alignment
        self.spacing = spacing

    def render(self, renderer: UIRenderer) -> None:
        """Render children."""
        # Containers usually don't render themselves, just children
        # But we could draw a debug background here if needed
        for child in self.children:
            child.render(renderer)

    def layout(self) -> None:
        """Recalculate positions based on alignment and direction."""
        if not self.children:
            return

        # 1. Calculate total used space
        total_size = 0
        visible_children = [c for c in self.children if c.visible]

        for child in visible_children:
            if self.direction == LayoutDirection.VERTICAL:
                total_size += child.rect.height
            else:
                total_size += child.rect.width

        total_size += self.spacing * (len(visible_children) - 1)

        # 2. Determine Start Offset based on Alignment
        start_offset = 0
        if self.alignment == LayoutAlignment.CENTER:
            container_size = (
                self.rect.height
                if self.direction == LayoutDirection.VERTICAL
                else self.rect.width
            )
            start_offset = (container_size - total_size) // 2
        elif self.alignment == LayoutAlignment.END:
            container_size = (
                self.rect.height
                if self.direction == LayoutDirection.VERTICAL
                else self.rect.width
            )
            start_offset = container_size - total_size

        # 3. Position Children
        current_x = self.rect.x
        current_y = self.rect.y

        if self.direction == LayoutDirection.VERTICAL:
            current_y += start_offset
        else:
            current_x += start_offset

        for child in visible_children:
            child.rect.x = current_x
            child.rect.y = current_y

            if self.direction == LayoutDirection.VERTICAL:
                current_y += child.rect.height + self.spacing
                # Handle cross-axis alignment (e.g. center horizontally in a vertical box)
                child.rect.x = self.rect.x + (self.rect.width - child.rect.width) // 2
            else:
                current_x += child.rect.width + self.spacing
                # Handle cross-axis alignment
                child.rect.y = self.rect.y + (self.rect.height - child.rect.height) // 2
