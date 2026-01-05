"""Image display component."""

from typing import Any, Optional
from pyguara.common.types import Vector2, Color
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget


class Image(Widget):
    """Displays a texture or image."""

    def __init__(
        self,
        texture: Any,
        position: Vector2,
        size: Vector2,
        color: Optional[Color] = None,
    ) -> None:
        """Initialize the image widget."""
        super().__init__(position, size)
        self.texture = texture
        self.tint_color = color

    def render(self, renderer: UIRenderer) -> None:
        """Render the texture."""
        if self.texture:
            renderer.draw_texture(self.texture, self.rect, self.tint_color)
