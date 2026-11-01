"""A container drawn from a nine-patch plate rather than a flat rectangle."""

from typing import Any

from pyguara.common.types import Color, Vector2
from pyguara.graphics.ninepatch import NinePatchSprite, render_ninepatch
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.components.widget import Widget


class NinePatchPanel(Widget):
    """A `Panel` whose background is a nine-patch.

    Its own widget rather than a `nine_patch=` argument on `Panel`, because
    almost nothing else about `Panel` applies: the theme's border, corner
    radius, surface colour and shadow are all things the plate's art already
    is. `BevelPanel` is the same call for the same reason.

    The texture is taken resolved, exactly as `Image` takes one, because a
    `UIRenderer` draws a backend surface and `sprite.texture_path` does not
    name one.
    """

    def __init__(
        self,
        texture: Any,
        sprite: NinePatchSprite,
        position: Vector2,
        size: Vector2,
        color: Color | None = None,
    ) -> None:
        """Initialize the panel.

        Args:
            texture: The surface to slice, as `UIRenderer.draw_texture` takes it.
            sprite: The edges, and the region of `texture` if it is an atlas.
            position: Top-left corner.
            size: Width and height. Below the sum of the edges it draws at
                that sum, so the corners never overlap.
            color: Tint, if any.
        """
        super().__init__(position, size)
        self.texture = texture
        self.sprite = sprite
        self.tint_color = color

    def render(self, renderer: UIRenderer) -> None:
        """Render the plate, then the children on top of it."""
        render_ninepatch(
            renderer,
            self.sprite,
            self.texture,
            int(self.rect.x),
            int(self.rect.y),
            int(self.rect.width),
            int(self.rect.height),
            self.tint_color,
        )
        for child in self.children:
            if child.visible:
                child.render(renderer)
