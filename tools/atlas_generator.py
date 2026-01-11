#!/usr/bin/env python3
"""
Sprite Atlas Generator CLI Tool

Packs multiple sprite images into a single texture atlas using a shelf-packing
algorithm. Generates both the packed image and JSON metadata for runtime loading.

Usage:
    python -m tools.atlas_generator \
        --input assets/sprites/ \
        --output assets/atlas/characters.png \
        --metadata assets/atlas/characters.json \
        --size 2048 \
        --padding 2
"""

from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import List, Tuple, Dict, Optional

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow is required for atlas generation.")
    print("Install it with: pip install Pillow")
    sys.exit(1)


class PackedSprite:
    """Represents a sprite that has been packed into the atlas."""

    def __init__(
        self,
        name: str,
        image: Image.Image,
        x: int,
        y: int,
        width: int,
        height: int,
    ):
        """
        Initialize packed sprite data.

        Args:
            name (str): Sprite identifier (filename without extension).
            image (Image.Image): The sprite image.
            x (int): X position in atlas.
            y (int): Y position in atlas.
            width (int): Sprite width.
            height (int): Sprite height.
        """
        self.name = name
        self.image = image
        self.x = x
        self.y = y
        self.width = width
        self.height = height


class Shelf:
    """Represents a horizontal shelf in the shelf-packing algorithm."""

    def __init__(self, y: int, height: int, max_width: int):
        """
        Initialize a shelf.

        Args:
            y (int): Y position of the shelf.
            height (int): Height of the shelf.
            max_width (int): Maximum width available.
        """
        self.y = y
        self.height = height
        self.max_width = max_width
        self.current_x = 0

    def can_fit(self, width: int, height: int) -> bool:
        """
        Check if a sprite can fit on this shelf.

        Args:
            width (int): Sprite width.
            height (int): Sprite height.

        Returns:
            bool: True if the sprite fits, False otherwise.
        """
        return (
            self.current_x + width <= self.max_width and height <= self.height
        )

    def add(self, width: int) -> int:
        """
        Add a sprite to this shelf and return its X position.

        Args:
            width (int): Sprite width.

        Returns:
            int: The X position where the sprite was placed.
        """
        x = self.current_x
        self.current_x += width
        return x


class AtlasGenerator:
    """
    Generates sprite atlases using a shelf-packing algorithm.

    The algorithm sorts sprites by height (descending) and packs them
    into horizontal shelves, creating new shelves as needed.
    """

    def __init__(
        self,
        atlas_size: int = 2048,
        padding: int = 2,
        allow_rotation: bool = False,
    ):
        """
        Initialize the atlas generator.

        Args:
            atlas_size (int): Maximum atlas dimension (width and height).
            padding (int): Padding between sprites to prevent bleeding.
            allow_rotation (bool): Whether to allow 90-degree rotation (not implemented).
        """
        self.atlas_size = atlas_size
        self.padding = padding
        self.allow_rotation = allow_rotation

    def load_images(self, input_path: Path) -> List[Tuple[str, Image.Image]]:
        """
        Load all images from a directory.

        Args:
            input_path (Path): Directory containing sprite images.

        Returns:
            List[Tuple[str, Image.Image]]: List of (name, image) tuples.

        Raises:
            ValueError: If no images found or path is invalid.
        """
        if not input_path.exists():
            raise ValueError(f"Input path does not exist: {input_path}")

        if not input_path.is_dir():
            raise ValueError(f"Input path is not a directory: {input_path}")

        images = []
        supported_formats = {".png", ".jpg", ".jpeg", ".bmp", ".tga"}

        for file_path in sorted(input_path.iterdir()):
            if file_path.suffix.lower() in supported_formats:
                try:
                    img = Image.open(file_path)
                    # Convert to RGBA to ensure consistent format
                    if img.mode != "RGBA":
                        img = img.convert("RGBA")
                    name = file_path.stem  # Filename without extension
                    images.append((name, img))
                except Exception as e:
                    print(f"Warning: Failed to load {file_path}: {e}")
                    continue

        if not images:
            raise ValueError(f"No valid images found in {input_path}")

        return images

    def pack(
        self, images: List[Tuple[str, Image.Image]]
    ) -> Tuple[Image.Image, Dict[str, dict]]:
        """
        Pack images into an atlas using shelf-packing algorithm.

        Args:
            images (List[Tuple[str, Image.Image]]): List of (name, image) tuples.

        Returns:
            Tuple[Image.Image, Dict[str, dict]]: The atlas image and metadata dict.

        Raises:
            ValueError: If sprites don't fit in atlas size.
        """
        # Sort images by height (descending) for better packing
        sorted_images = sorted(
            images, key=lambda x: x[1].height, reverse=True
        )

        # Create blank atlas with transparency
        atlas = Image.new("RGBA", (self.atlas_size, self.atlas_size), (0, 0, 0, 0))

        shelves: List[Shelf] = []
        packed_sprites: List[PackedSprite] = []
        current_y = 0

        for name, img in sorted_images:
            width = img.width + self.padding * 2
            height = img.height + self.padding * 2

            # Try to fit on existing shelves
            placed = False
            for shelf in shelves:
                if shelf.can_fit(width, height):
                    x = shelf.add(width)
                    packed_sprites.append(
                        PackedSprite(
                            name,
                            img,
                            x + self.padding,
                            shelf.y + self.padding,
                            img.width,
                            img.height,
                        )
                    )
                    placed = True
                    break

            # Create new shelf if needed
            if not placed:
                if current_y + height > self.atlas_size:
                    raise ValueError(
                        f"Atlas size {self.atlas_size}x{self.atlas_size} "
                        f"is too small to fit all sprites. "
                        f"Try increasing --size or reducing sprite count."
                    )

                shelf = Shelf(current_y, height, self.atlas_size)
                x = shelf.add(width)
                packed_sprites.append(
                    PackedSprite(
                        name,
                        img,
                        x + self.padding,
                        current_y + self.padding,
                        img.width,
                        img.height,
                    )
                )
                shelves.append(shelf)
                current_y += height

        # Paste sprites into atlas
        for sprite in packed_sprites:
            atlas.paste(sprite.image, (sprite.x, sprite.y), sprite.image)

        # Build metadata dictionary
        metadata = {
            "atlas_size": [self.atlas_size, self.atlas_size],
            "padding": self.padding,
            "sprite_count": len(packed_sprites),
            "regions": {
                sprite.name: {
                    "x": sprite.x,
                    "y": sprite.y,
                    "width": sprite.width,
                    "height": sprite.height,
                    "original_size": [sprite.width, sprite.height],
                }
                for sprite in packed_sprites
            },
        }

        return atlas, metadata

    def generate(
        self,
        input_path: Path,
        output_path: Path,
        metadata_path: Optional[Path] = None,
    ) -> None:
        """
        Generate atlas from input directory.

        Args:
            input_path (Path): Directory containing sprite images.
            output_path (Path): Path for output atlas image.
            metadata_path (Optional[Path]): Path for JSON metadata file.
        """
        print(f"Loading images from: {input_path}")
        images = self.load_images(input_path)
        print(f"Loaded {len(images)} images")

        print("Packing atlas...")
        atlas_image, metadata = self.pack(images)

        # Create output directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Save atlas image
        print(f"Saving atlas to: {output_path}")
        atlas_image.save(output_path, "PNG")

        # Save metadata if requested
        if metadata_path:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"Saving metadata to: {metadata_path}")
            with open(metadata_path, "w") as f:
                json.dump(metadata, f, indent=2)

        print(
            f"Atlas generation complete: {metadata['sprite_count']} sprites packed"
        )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate sprite atlas from multiple images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python -m tools.atlas_generator -i assets/sprites/ -o atlas.png

  # With metadata
  python -m tools.atlas_generator -i assets/sprites/ -o atlas.png -m atlas.json

  # Custom size and padding
  python -m tools.atlas_generator -i assets/sprites/ -o atlas.png -s 4096 -p 4
        """,
    )

    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        required=True,
        help="Input directory containing sprite images",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output path for atlas image (PNG)",
    )
    parser.add_argument(
        "-m",
        "--metadata",
        type=Path,
        help="Output path for JSON metadata (optional)",
    )
    parser.add_argument(
        "-s",
        "--size",
        type=int,
        default=2048,
        help="Atlas size (width and height, default: 2048)",
    )
    parser.add_argument(
        "-p",
        "--padding",
        type=int,
        default=2,
        help="Padding between sprites (default: 2)",
    )

    args = parser.parse_args()

    try:
        generator = AtlasGenerator(
            atlas_size=args.size,
            padding=args.padding,
        )
        generator.generate(
            input_path=args.input,
            output_path=args.output,
            metadata_path=args.metadata,
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
