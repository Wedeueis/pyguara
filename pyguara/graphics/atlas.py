"""
Sprite atlas (texture packing) data structures for optimized rendering.

A sprite atlas combines multiple small textures into a single large texture,
reducing draw calls and improving GPU batching efficiency. This is essential
for rendering many different sprites at high framerates.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional

from pyguara.common.types import Rect
from pyguara.resources.types import Texture


@dataclass
class AtlasRegion:
    """
    Represents a sub-region within a sprite atlas.

    Attributes:
        name (str): Unique identifier for this region (typically filename without extension).
        rect (Rect): Position and size within the atlas texture (x, y, width, height).
        original_size (tuple[int, int]): Original image dimensions before packing.
    """

    name: str
    rect: Rect
    original_size: tuple[int, int]


class Atlas:
    """
    A collection of packed sprites within a single texture.

    Provides fast lookup of sprite regions by name and supports
    sub-texture extraction for rendering.

    Attributes:
        texture (Texture): The packed atlas texture.
        regions (Dict[str, AtlasRegion]): Mapping of sprite names to their regions.
    """

    def __init__(self, texture: Texture, regions: Dict[str, AtlasRegion]):
        """
        Initialize the atlas.

        Args:
            texture (Texture): The packed atlas texture.
            regions (Dict[str, AtlasRegion]): Mapping of sprite names to regions.
        """
        self.texture = texture
        self.regions = regions

    def get_region(self, name: str) -> Optional[AtlasRegion]:
        """
        Get a sprite region by name.

        Args:
            name (str): The sprite name to look up.

        Returns:
            Optional[AtlasRegion]: The region if found, None otherwise.
        """
        return self.regions.get(name)

    def get_rect(self, name: str) -> Optional[Rect]:
        """
        Get the rectangle for a sprite region.

        Args:
            name (str): The sprite name to look up.

        Returns:
            Optional[Rect]: The region's rect if found, None otherwise.
        """
        region = self.get_region(name)
        return region.rect if region else None

    def has_region(self, name: str) -> bool:
        """
        Check if the atlas contains a sprite region.

        Args:
            name (str): The sprite name to check.

        Returns:
            bool: True if the region exists, False otherwise.
        """
        return name in self.regions

    def list_regions(self) -> list[str]:
        """
        Get a list of all sprite names in this atlas.

        Returns:
            list[str]: List of sprite region names.
        """
        return list(self.regions.keys())

    @property
    def region_count(self) -> int:
        """
        Get the number of sprites packed in this atlas.

        Returns:
            int: Number of regions.
        """
        return len(self.regions)
