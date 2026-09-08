"""Layout containers."""

from pyguara.common.types import Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.base import UIElement
from pyguara.ui.types import LayoutAlignment, LayoutDirection


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
            if child.visible:
                child.render(renderer)

    def layout(self, available_rect: Rect, renderer: UIRenderer) -> None:
        """Recalculate child positions based on alignment and direction.

        Overrides `UIElement.layout`: the container first resolves its own
        rect (its `constraints` against `available_rect`, if any), then
        measures every visible child and stacks them along `direction`,
        distributing free space per `alignment` on the main axis and either
        centring or stretching them on the cross axis. Nested containers are
        laid out recursively afterwards.

        Args:
            available_rect: The rectangle this container may occupy.
            renderer: Passed to each visible child's `measure()` before its
                size is read, so text-sized children stack correctly.
        """
        self.measure(renderer)
        if self.constraints:
            self.rect = self.constraints.apply(self.rect, available_rect)

        visible_children = [c for c in self.children if c.visible]
        if not visible_children:
            return

        is_vertical = self.direction == LayoutDirection.VERTICAL

        # 1. Measure children, then sum the space they need on the main axis.
        for child in visible_children:
            child.measure(renderer)

        total_size = sum(
            child.rect.height if is_vertical else child.rect.width
            for child in visible_children
        )
        total_size += self.spacing * (len(visible_children) - 1)

        # 2. Distribute free space on the main axis per alignment.
        container_main = self.rect.height if is_vertical else self.rect.width
        start_offset = 0
        if self.alignment == LayoutAlignment.CENTER:
            start_offset = (container_main - total_size) // 2
        elif self.alignment == LayoutAlignment.END:
            start_offset = container_main - total_size

        # 3. Position children.
        current_x = self.rect.x + (0 if is_vertical else start_offset)
        current_y = self.rect.y + (start_offset if is_vertical else 0)
        stretch = self.alignment == LayoutAlignment.STRETCH

        for child in visible_children:
            if is_vertical:
                child.rect.y = current_y
                current_y += child.rect.height + self.spacing
                if stretch:
                    child.rect.x = self.rect.x
                    child.rect.width = self.rect.width
                else:
                    child.rect.x = (
                        self.rect.x + (self.rect.width - child.rect.width) // 2
                    )
            else:
                child.rect.x = current_x
                current_x += child.rect.width + self.spacing
                if stretch:
                    child.rect.y = self.rect.y
                    child.rect.height = self.rect.height
                else:
                    child.rect.y = (
                        self.rect.y + (self.rect.height - child.rect.height) // 2
                    )

        # 4. Recurse into children that have their own subtree, so a nested
        #    container stacks its own children against the slot it was just
        #    given.
        for child in visible_children:
            if child.children:
                child.layout(child.rect, renderer)
