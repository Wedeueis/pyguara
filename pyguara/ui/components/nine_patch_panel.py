"""A container drawn from a nine-patch plate rather than a flat rectangle."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pyguara.common.types import Color, Vector2
from pyguara.graphics.ninepatch import NinePatchSprite, render_ninepatch
from pyguara.graphics.protocols import UIRenderer
from pyguara.resources.types import Texture
from pyguara.ui.components.widget import Widget

if TYPE_CHECKING:
    from pyguara.resources.manager import ResourceManager


class NinePatchPanel(Widget):
    """A `Panel` whose background is a nine-patch.

    Its own widget rather than a `nine_patch=` argument on `Panel`, because
    almost nothing else about `Panel` applies: the theme's border, corner
    radius, surface colour and shadow are all things the plate's art already
    is. `BevelPanel` is the same call for the same reason.

    The texture is taken resolved, exactly as `Image` takes one. To load it from
    `sprite.texture_path`, use `from_resources`.
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
            texture: What to slice: a `resources.Texture` or a surface.
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

    @classmethod
    def from_resources(
        cls,
        resources: ResourceManager,
        sprite: NinePatchSprite,
        position: Vector2,
        size: Vector2,
        color: Color | None = None,
    ) -> NinePatchPanel:
        """Build a panel, loading its texture from `sprite.texture_path`.

        Args:
            resources: The manager to load through, so the texture is cached
                and released like any other.
            sprite: The edges, and the path of the texture to load.
            position: Top-left corner.
            size: Width and height.
            color: Tint, if any.

        Returns:
            The panel.
        """
        texture = resources.load(sprite.texture_path, Texture)  # type: ignore[type-abstract]
        return cls(texture, sprite, position, size, color)

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
