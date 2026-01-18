"""Concrete loaders for Pygame assets."""

import logging
from typing import List, Optional
import pygame
from pyguara.resources.loader import IMetaAwareLoader
from pyguara.resources.types import Resource
from pyguara.resources.meta import AssetMeta, TextureMeta
from .types import PygameTexture

logger = logging.getLogger(__name__)


class PygameImageLoader(IMetaAwareLoader):
    """Load image files into PygameTexture objects with meta support.

    Supports the following meta settings:
    - filter: "nearest" (pixelated) or "linear" (smooth)
    - premultiply_alpha: Pre-multiply RGB by alpha for correct blending
    - srgb: Whether texture is in sRGB color space (affects convert_alpha)
    """

    @property
    def supported_extensions(self) -> List[str]:
        """Returns a list of supported extensions."""
        return [".png", ".jpg", ".jpeg", ".bmp", ".tga"]

    def load(self, path: str) -> Resource:
        """Load a Texture with default settings.

        Note:
            Requires pygame.display.set_mode() to be called beforehand
            if internal format conversion is performed.
        """
        return self.load_with_meta(path, None)

    def load_with_meta(self, path: str, meta: Optional[AssetMeta]) -> Resource:
        """Load a Texture with optional metadata settings.

        Args:
            path: Path to the image file.
            meta: Optional TextureMeta with import settings.

        Returns:
            PygameTexture with meta settings applied.
        """
        # Get texture meta (use defaults if none provided)
        texture_meta: TextureMeta
        if isinstance(meta, TextureMeta):
            texture_meta = meta
        else:
            texture_meta = TextureMeta()

        # Load the surface
        surface = pygame.image.load(path)

        # Apply convert_alpha for proper alpha handling
        if pygame.display.get_surface() is not None:
            surface = surface.convert_alpha()

        # Apply premultiply alpha if requested
        if texture_meta.premultiply_alpha:
            surface = self._premultiply_alpha(surface)

        # Note: Pygame doesn't support runtime texture filtering changes
        # The filter setting is stored in the meta for backends that support it
        # (like ModernGL). For pygame, we log a debug message.
        if texture_meta.filter != "nearest":
            logger.debug(
                "Texture filter '%s' requested for '%s' - pygame uses nearest by default",
                texture_meta.filter,
                path,
            )

        return PygameTexture(path, surface)

    def _premultiply_alpha(self, surface: pygame.Surface) -> pygame.Surface:
        """Premultiply RGB values by alpha for correct blending.

        Args:
            surface: Input surface with RGBA data.

        Returns:
            New surface with premultiplied alpha.
        """
        # Get pixel array for manipulation
        try:
            import pygame.surfarray as surfarray

            # Lock surface for array access
            arr = surfarray.pixels3d(surface)
            alpha = surfarray.pixels_alpha(surface)

            # Premultiply: RGB = RGB * (A / 255)
            alpha_factor = alpha / 255.0
            arr[:, :, 0] = (arr[:, :, 0] * alpha_factor).astype("uint8")
            arr[:, :, 1] = (arr[:, :, 1] * alpha_factor).astype("uint8")
            arr[:, :, 2] = (arr[:, :, 2] * alpha_factor).astype("uint8")

            del arr
            del alpha

            return surface

        except (ImportError, pygame.error) as e:
            logger.warning("Could not premultiply alpha: %s", e)
            return surface
