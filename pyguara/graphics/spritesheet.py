"""
Utilities for handling sprite sheet assets.

This module provides the logic to slice a single large texture into multiple
smaller sub-textures (frames) that can be played back by the animation system.

The implementation is backend-agnostic, using Pillow for image manipulation
and a TextureFactory protocol for creating backend-specific textures.
"""

from typing import List

from PIL import Image

from pyguara.resources.types import Texture
from pyguara.graphics.protocols import TextureFactory


class SpriteSheet:
    """A utility for slicing sprite sheet images into individual frames.

    This class loads a sprite sheet image and can slice it into a grid of
    equal-sized frames. It uses Pillow for image manipulation, making it
    independent of the rendering backend (Pygame or ModernGL).

    Example:
        factory = container.get(TextureFactory)
        sheet = SpriteSheet("assets/sprites/player.png", factory)
        frames = sheet.slice_grid(32, 32)  # 32x32 pixel frames

        # Or with a PIL Image directly (useful for testing):
        img = Image.new("RGBA", (64, 64))
        sheet = SpriteSheet.from_image(img, factory, "test_sheet")
    """

    def __init__(self, image_path: str, factory: TextureFactory) -> None:
        """Initialize the sprite sheet from a file path.

        Args:
            image_path: Path to the sprite sheet image file.
            factory: Factory for creating backend-specific textures.
        """
        self._path = image_path
        self._factory = factory
        self._frames: List[Texture] = []

        # Load the image using Pillow
        self._image = Image.open(image_path).convert("RGBA")

    @classmethod
    def from_image(
        cls, image: Image.Image, factory: TextureFactory, name: str = "sprite_sheet"
    ) -> "SpriteSheet":
        """Create a SpriteSheet from a PIL Image directly.

        Useful for testing or when the image is already in memory.

        Args:
            image: A PIL Image object (will be converted to RGBA).
            factory: Factory for creating backend-specific textures.
            name: Identifier for the sprite sheet (used in frame names).

        Returns:
            A new SpriteSheet instance.
        """
        instance = cls.__new__(cls)
        instance._path = name
        instance._factory = factory
        instance._frames = []
        instance._image = image.convert("RGBA")
        return instance

    @property
    def width(self) -> int:
        """Get the width of the sprite sheet in pixels."""
        return self._image.width

    @property
    def height(self) -> int:
        """Get the height of the sprite sheet in pixels."""
        return self._image.height

    def slice_grid(
        self, frame_width: int, frame_height: int, count: int = 0
    ) -> List[Texture]:
        """Slice the sprite sheet into a grid of equal-sized frames.

        Frames are extracted left-to-right, top-to-bottom (row-major order).

        Args:
            frame_width: Width of a single frame in pixels.
            frame_height: Height of a single frame in pixels.
            count: Maximum number of frames to extract. If 0, extracts all
                   frames that fit in the grid.

        Returns:
            List of Texture objects, one for each extracted frame.
        """
        # Calculate grid dimensions
        cols = self._image.width // frame_width
        rows = self._image.height // frame_height

        total_possible = cols * rows
        frames_to_load = count if count > 0 else total_possible

        self._frames = []
        loaded = 0

        for y in range(rows):
            for x in range(cols):
                if loaded >= frames_to_load:
                    break

                # Calculate the crop box (left, upper, right, lower)
                left = x * frame_width
                upper = y * frame_height
                right = left + frame_width
                lower = upper + frame_height

                # Crop the frame from the sheet
                frame_image = self._image.crop((left, upper, right, lower))

                # Convert to raw RGBA bytes
                frame_data = frame_image.tobytes("raw", "RGBA")

                # Create texture using the factory
                frame_name = f"{self._path}_{loaded}"
                texture = self._factory.create_from_bytes(
                    frame_name, frame_data, frame_width, frame_height
                )

                self._frames.append(texture)
                loaded += 1

        return self._frames

    def slice_regions(self, regions: List[tuple[int, int, int, int]]) -> List[Texture]:
        """Slice specific regions from the sprite sheet.

        Useful for sprite sheets with irregular frame sizes or layouts.

        Args:
            regions: List of (x, y, width, height) tuples defining each frame.

        Returns:
            List of Texture objects, one for each specified region.
        """
        textures: List[Texture] = []

        for i, (x, y, width, height) in enumerate(regions):
            # Crop the region
            frame_image = self._image.crop((x, y, x + width, y + height))

            # Convert to raw RGBA bytes
            frame_data = frame_image.tobytes("raw", "RGBA")

            # Create texture using the factory
            frame_name = f"{self._path}_region_{i}"
            texture = self._factory.create_from_bytes(
                frame_name, frame_data, width, height
            )

            textures.append(texture)

        return textures

    @property
    def frames(self) -> List[Texture]:
        """Get the list of previously sliced frames."""
        return self._frames
