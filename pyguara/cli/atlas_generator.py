#!/usr/bin/env python3
"""Sprite Atlas Generator CLI Tool.

Pack multiple sprite images into a single texture atlas using a shelf-packing
algorithm. Generate both the packed image and JSON metadata for runtime loading.

Usage:
    pyguara atlas -i assets/sprites/ -o atlas.png -m atlas.json
    python -m pyguara.cli.atlas_generator --input assets/sprites/ --output atlas.png
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

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
        return self.current_x + width <= self.max_width and height <= self.height

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
    ):
        """
        Initialize the atlas generator.

        Args:
            atlas_size (int): Maximum atlas dimension (width and height).
            padding (int): Padding between sprites to prevent bleeding.
        """
        self.atlas_size = atlas_size
        self.padding = padding

    def load_images(
        self,
        input_path: Path,
        exclude: set[Path] | None = None,
    ) -> list[tuple[str, Image.Image]]:
        """
        Load all images from a directory.

        Args:
            input_path (Path): Directory containing sprite images.
            exclude (Optional[Set[Path]]): Resolved paths to skip (e.g. the
                atlas the caller is about to write into this same directory).

        Returns:
            List[Tuple[str, Image.Image]]: List of (name, image) tuples.

        Raises:
            ValueError: If no images found, the path is invalid, or two files
                share a stem (``hero.png`` and ``hero.jpg`` would both claim the
                region name ``hero`` and silently overwrite each other).
        """
        if not input_path.exists():
            raise ValueError(f"Input path does not exist: {input_path}")

        if not input_path.is_dir():
            raise ValueError(f"Input path is not a directory: {input_path}")

        excluded = exclude or set()
        images: list[tuple[str, Image.Image]] = []
        stems: dict[str, list[str]] = {}
        supported_formats = {".png", ".jpg", ".jpeg", ".bmp", ".tga"}

        for file_path in sorted(input_path.iterdir()):
            if file_path.suffix.lower() not in supported_formats:
                continue
            if file_path.resolve() in excluded:
                continue
            try:
                img: Image.Image = Image.open(file_path)
                # Convert to RGBA to ensure consistent format
                if img.mode != "RGBA":
                    img = img.convert("RGBA")
                name = file_path.stem  # Filename without extension
                stems.setdefault(name, []).append(file_path.name)
                images.append((name, img))
            except Exception as e:
                print(f"Warning: Failed to load {file_path}: {e}")
                continue

        collisions = {stem: files for stem, files in stems.items() if len(files) > 1}
        if collisions:
            detail = "; ".join(
                f"{stem!r} <- {', '.join(sorted(files))}"
                for stem, files in sorted(collisions.items())
            )
            raise ValueError(
                f"Multiple files map to the same atlas region name in "
                f"{input_path}: {detail}. Rename or remove the duplicates."
            )

        if not images:
            raise ValueError(f"No valid images found in {input_path}")

        return images

    def pack(
        self, images: list[tuple[str, Image.Image]]
    ) -> tuple[Image.Image, dict[str, Any]]:
        """
        Pack images into an atlas using shelf-packing algorithm.

        Args:
            images (List[Tuple[str, Image.Image]]): List of (name, image) tuples.

        Returns:
            Tuple[Image.Image, Dict[str, Any]]: The atlas image and metadata dict.

        Raises:
            ValueError: If two sprites share a name, or a sprite does not fit
                the atlas in either dimension.
        """
        names = [name for name, _ in images]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(
                f"Duplicate sprite name(s) passed to pack(): {', '.join(dupes)}. "
                f"Region names must be unique."
            )

        # Sort images by height (descending) for better packing
        sorted_images = sorted(images, key=lambda x: x[1].height, reverse=True)

        # Create blank atlas with transparency
        atlas = Image.new("RGBA", (self.atlas_size, self.atlas_size), (0, 0, 0, 0))

        shelves: list[Shelf] = []
        packed_sprites: list[PackedSprite] = []
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
                # Guard both dimensions: a sprite wider than the atlas used to
                # slip past this check (only height was tested) and get silently
                # clipped by Image.paste while its metadata kept the full width.
                if width > self.atlas_size or current_y + height > self.atlas_size:
                    raise ValueError(
                        f"Atlas size {self.atlas_size}x{self.atlas_size} "
                        f"is too small to fit all sprites "
                        f"(sprite {name!r} needs {width}x{height}px including "
                        f"padding). Try increasing --size or reducing sprite count."
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
        metadata_path: Path | None = None,
    ) -> None:
        """
        Generate atlas from input directory.

        Args:
            input_path (Path): Directory containing sprite images.
            output_path (Path): Path for output atlas image.
            metadata_path (Optional[Path]): Path for JSON metadata file.
        """
        # Never re-ingest our own output when it is written back into the
        # input directory (a common -i/-o overlap).
        exclude = {output_path.resolve()}
        if metadata_path is not None:
            exclude.add(metadata_path.resolve())

        print(f"Loading images from: {input_path}")
        images = self.load_images(input_path, exclude=exclude)
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

        print(f"Atlas generation complete: {metadata['sprite_count']} sprites packed")


@click.command()
@click.option(
    "-i",
    "--input",
    "input_dir",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    required=True,
    help="Input directory containing sprite images",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    required=True,
    help="Output path for atlas image (PNG)",
)
@click.option(
    "-m",
    "--metadata",
    type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
    default=None,
    help="Output path for JSON metadata (optional)",
)
@click.option(
    "-s",
    "--size",
    type=int,
    default=2048,
    help="Atlas size (width and height, default: 2048)",
)
@click.option(
    "-p",
    "--padding",
    type=int,
    default=2,
    help="Padding between sprites (default: 2)",
)
def atlas(
    input_dir: Path,
    output: Path,
    metadata: Path | None,
    size: int,
    padding: int,
) -> None:  # noqa: D301  (\b is Click's no-wrap marker; r""" would defeat it)
    """Generate a sprite atlas from multiple images.

    Pack sprites from INPUT directory into a single texture atlas using
    shelf-packing algorithm.

    \b
    Examples:
      # Basic usage
      pyguara atlas -i assets/sprites/ -o atlas.png
      # With metadata
      pyguara atlas -i assets/sprites/ -o atlas.png -m atlas.json
      # Custom size and padding
      pyguara atlas -i assets/sprites/ -o atlas.png -s 4096 -p 4
    """
    try:
        generator = AtlasGenerator(
            atlas_size=size,
            padding=padding,
        )
        generator.generate(
            input_path=input_dir,
            output_path=output,
            metadata_path=metadata,
        )
    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        raise SystemExit(1) from e


def main() -> None:
    """Entry point for ``python -m pyguara.cli.atlas_generator``.

    Delegates straight to the :func:`atlas` Click command so the module-level
    invocation and ``pyguara atlas`` share one option surface and one code
    path (they used to be a hand-kept argparse copy that could drift).
    """
    atlas.main(prog_name="pyguara.cli.atlas_generator")


if __name__ == "__main__":
    main()
