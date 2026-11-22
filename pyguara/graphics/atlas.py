"""Sprite atlas (texture packing) data structures for optimized rendering.

A sprite atlas combines multiple small textures into a few large ones,
so sprites drawn from one texture batch together instead of breaking the
batch per image. `pyguara atlas` builds one; `ResourceManager.load_atlas`
reads it back.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyguara.common.types import Rect, Vector2
from pyguara.resources.types import Texture


@dataclass
class AtlasRegion:
    """Represents a sub-region within a sprite atlas.

    A trimmed region is smaller than its source image: the transparent
    border was cut off when packing. `offset` is where the kept part sat in
    the source, so drawing at `offset` inside an `original_size` box puts
    every pixel where the untrimmed image had it.

    Attributes:
        name (str): Unique identifier for this region (typically filename without extension).
        rect (Rect): Position and size within its page's texture.
        original_size (tuple[int, int]): The source image's size before trimming.
        offset (tuple[int, int]): Where `rect`'s top-left sat in the source image.
        page (int): Which of the atlas's textures holds the region.
    """

    name: str
    rect: Rect
    original_size: tuple[int, int]
    offset: tuple[int, int] = (0, 0)
    page: int = 0

    @property
    def trimmed(self) -> bool:
        """Whether packing cut a transparent border off the source image."""
        return (self.rect.width, self.rect.height) != tuple(self.original_size)

    @property
    def center_offset(self) -> Vector2:
        """How far the region's centre is from the source image's centre.

        A renderer draws a sprite centred on its position, so add this to the
        position to draw a trimmed region exactly where the whole image was.
        """
        width, height = self.original_size
        return Vector2(
            self.offset[0] + self.rect.width / 2 - width / 2,
            self.offset[1] + self.rect.height / 2 - height / 2,
        )


class Atlas:
    """A collection of packed sprites within one or more textures.

    Provides fast lookup of sprite regions by name. An atlas too big for one
    texture has several pages, and each region names its own.

    Attributes:
        pages (list[Texture]): The packed textures, page 0 first.
        regions (Dict[str, AtlasRegion]): Mapping of sprite names to their regions.
    """

    def __init__(
        self,
        texture: Texture,
        regions: dict[str, AtlasRegion],
        pages: list[Texture] | None = None,
    ):
        """Initialize the atlas.

        Args:
            texture (Texture): The first page's texture.
            regions (Dict[str, AtlasRegion]): Mapping of sprite names to regions.
            pages: Every page's texture, `texture` first. None means one page.

        Raises:
            ValueError: If `pages` does not start with `texture`, or a region
                names a page the atlas does not have.
        """
        self.pages = [texture] if pages is None else list(pages)
        if not self.pages or self.pages[0] is not texture:
            raise ValueError("an atlas's pages must start with its texture")
        for region in regions.values():
            if not 0 <= region.page < len(self.pages):
                raise ValueError(
                    f"region {region.name!r} is on page {region.page}, but the "
                    f"atlas has {len(self.pages)}"
                )
        self.regions = regions

    @property
    def texture(self) -> Texture:
        """The first page's texture, the only one of a one-page atlas."""
        return self.pages[0]

    def texture_of(self, name: str) -> Texture | None:
        """Return the texture the region `name` is on, or None if there is none."""
        region = self.regions.get(name)
        return self.pages[region.page] if region else None

    def get_region(self, name: str) -> AtlasRegion | None:
        """Get a sprite region by name.

        Args:
            name (str): The sprite name to look up.

        Returns:
            Optional[AtlasRegion]: The region if found, None otherwise.
        """
        return self.regions.get(name)

    def get_rect(self, name: str) -> Rect | None:
        """Get the rectangle for a sprite region.

        Args:
            name (str): The sprite name to look up.

        Returns:
            Optional[Rect]: The region's rect if found, None otherwise.
        """
        region = self.get_region(name)
        return region.rect if region else None

    def has_region(self, name: str) -> bool:
        """Check if the atlas contains a sprite region.

        Args:
            name (str): The sprite name to check.

        Returns:
            bool: True if the region exists, False otherwise.
        """
        return name in self.regions

    def list_regions(self) -> list[str]:
        """Get a list of all sprite names in this atlas.

        Returns:
            list[str]: List of sprite region names.
        """
        return list(self.regions.keys())

    @property
    def region_count(self) -> int:
        """Get the number of sprites packed in this atlas.

        Returns:
            int: Number of regions.
        """
        return len(self.regions)
