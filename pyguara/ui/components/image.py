"""Image display component."""

from typing import Any

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget


class Image(Widget):
    """Displays a texture or image."""

    def __init__(
        self,
        texture: Any,
        position: Vector2,
        size: Vector2,
        color: Color | None = None,
        source_rect: Rect | None = None,
    ) -> None:
        """Initialize the image widget.

        Args:
            texture: The backend texture to draw.
            position: Top-left corner.
            size: Width and height.
            color: Tint, if any.
            source_rect: The region of `texture` to draw, in texture pixels.
                None draws all of it.
        """
        super().__init__(position, size)
        self.texture = texture
        self.tint_color = color
        self.source_rect = source_rect

    def render(self, renderer: UIRenderer) -> None:
        """Render the texture."""
        if self.texture:
            renderer.draw_texture(
                self.texture, self.rect, self.tint_color, self.source_rect
            )
