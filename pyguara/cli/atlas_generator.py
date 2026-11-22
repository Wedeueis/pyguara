#!/usr/bin/env python3
"""Sprite Atlas Generator CLI Tool.

Pack multiple sprite images into texture atlas pages using a shelf-packing
algorithm. Generate both the packed images and JSON metadata for runtime loading.

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
        page: int = 0,
        offset: tuple[int, int] = (0, 0),
        original_size: tuple[int, int] | None = None,
    ):
        """Initialize packed sprite data.

        Args:
            name (str): Sprite identifier (filename without extension).
            image (Image.Image): The sprite image, trimmed if trimming is on.
            x (int): X position in its page.
            y (int): Y position in its page.
            width (int): Sprite width.
            height (int): Sprite height.
            page: Which page it is on.
            offset: Where the trimmed image sat in the source image.
            original_size: The source image's size. None means untrimmed.
        """
        self.name = name
        self.image = image
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.page = page
        self.offset = offset
        self.original_size = original_size or (width, height)


class Shelf:
    """Represents a horizontal shelf in the shelf-packing algorithm."""

    def __init__(self, y: int, height: int, max_width: int):
        """Initialize a shelf.

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
        """Check if a sprite can fit on this shelf.

        Args:
            width (int): Sprite width.
            height (int): Sprite height.

        Returns:
            bool: True if the sprite fits, False otherwise.
        """
        return self.current_x + width <= self.max_width and height <= self.height

    def add(self, width: int) -> int:
        """Add a sprite to this shelf and return its X position.

        Args:
            width (int): Sprite width.

        Returns:
            int: The X position where the sprite was placed.
        """
        x = self.current_x
        self.current_x += width
        return x


FITS = ("fixed", "tight", "pot")
"""How a page is sized once packed: the full `--size`, cropped to what it
holds, or cropped and rounded up to a power of two."""


class AtlasGenerator:
    """Generates sprite atlases using a shelf-packing algorithm.

    The algorithm sorts sprites by height (descending) and packs them
    into horizontal shelves, creating new shelves as needed, and a new page
    once a page is full.
    """

    def __init__(
        self,
        atlas_size: int = 2048,
        padding: int = 2,
        *,
        atlas_height: int | None = None,
        trim: bool = False,
        fit: str = "fixed",
    ):
        """Initialize the atlas generator.

        Args:
            atlas_size (int): Maximum page width, and height unless
                `atlas_height` is given.
            padding (int): Padding between sprites to prevent bleeding.
            atlas_height: Maximum page height, for a page that is not square.
            trim: Cut each sprite's transparent border off before packing.
            fit: One of `FITS`.

        Raises:
            ValueError: If a size is not positive, padding is negative, or
                `fit` is not one of `FITS`.
        """
        if atlas_size <= 0 or (atlas_height is not None and atlas_height <= 0):
            raise ValueError("an atlas page must be at least 1x1 pixel")
        if padding < 0:
            raise ValueError(f"padding cannot be negative, got {padding}")
        if fit not in FITS:
            raise ValueError(f"fit must be one of {', '.join(FITS)}, not {fit!r}")
        self.atlas_size = atlas_size
        self.atlas_height = atlas_height if atlas_height is not None else atlas_size
        self.padding = padding
        self.trim = trim
        self.fit = fit

    def load_images(
        self,
        input_path: Path,
        exclude: set[Path] | None = None,
    ) -> list[tuple[str, Image.Image]]:
        """Load all images from a directory.

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
                # Closed here, not when the image is collected: Pillow
                # reads lazily, and an open file cannot be replaced or
                # deleted on Windows. `convert` returns a loaded copy even
                # when the mode already matches.
                with Image.open(file_path) as opened:
                    img: Image.Image = opened.convert("RGBA")
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
        """Pack images into a one-page atlas.

        Args:
            images (List[Tuple[str, Image.Image]]): List of (name, image) tuples.

        Returns:
            Tuple[Image.Image, Dict[str, Any]]: The atlas image and metadata dict.

        Raises:
            ValueError: If two sprites share a name, a sprite does not fit a
                page in either dimension, or the sprites need several pages.
        """
        pages, metadata = self.pack_pages(images)
        if len(pages) > 1:
            raise ValueError(
                f"Atlas size {self.atlas_size}x{self.atlas_height} is too small "
                f"to fit all sprites on one page: they need {len(pages)}. "
                f"Increase --size, or write metadata (-m) to get several pages."
            )
        return pages[0], metadata

    def pack_pages(
        self, images: list[tuple[str, Image.Image]]
    ) -> tuple[list[Image.Image], dict[str, Any]]:
        """Pack images into as many pages as they need.

        Args:
            images: List of (name, image) tuples.

        Returns:
            The page images, and the metadata. Each region names its page;
            `pages` lists each page's size, and `generate()` adds its file.

        Raises:
            ValueError: If two sprites share a name, or a sprite does not fit
                a page in either dimension.
        """
        names = [name for name, _ in images]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(
                f"Duplicate sprite name(s) passed to pack(): {', '.join(dupes)}. "
                f"Region names must be unique."
            )

        sources = [
            (*(_trimmed(img) if self.trim else (img, (0, 0))), name, img.size)
            for name, img in images
        ]
        # Sort images by height (descending) for better packing; the name
        # breaks ties so the layout does not depend on the input order.
        sources.sort(key=lambda source: (-source[0].height, source[2]))

        page = 0
        shelves: list[Shelf] = []
        packed_sprites: list[PackedSprite] = []
        current_y = 0

        for img, offset, name, original_size in sources:
            width = img.width + self.padding * 2
            height = img.height + self.padding * 2
            if width > self.atlas_size or height > self.atlas_height:
                # Both dimensions: a sprite wider than the atlas would
                # otherwise be clipped by Image.paste while its metadata kept
                # the full width.
                raise ValueError(
                    f"Atlas size {self.atlas_size}x{self.atlas_height} "
                    f"is too small to fit all sprites "
                    f"(sprite {name!r} needs {width}x{height}px including "
                    f"padding). Try increasing --size or reducing sprite count."
                )

            shelf = next((s for s in shelves if s.can_fit(width, height)), None)
            if shelf is None:
                if current_y + height > self.atlas_height:
                    page += 1
                    shelves = []
                    current_y = 0
                shelf = Shelf(current_y, height, self.atlas_size)
                shelves.append(shelf)
                current_y += height
            x = shelf.add(width)
            packed_sprites.append(
                PackedSprite(
                    name,
                    img,
                    x + self.padding,
                    shelf.y + self.padding,
                    img.width,
                    img.height,
                    page=page,
                    offset=offset,
                    original_size=original_size,
                )
            )

        sizes = [self._page_size(packed_sprites, index) for index in range(page + 1)]
        pages = [Image.new("RGBA", size, (0, 0, 0, 0)) for size in sizes]
        for sprite in packed_sprites:
            pages[sprite.page].paste(sprite.image, (sprite.x, sprite.y), sprite.image)

        metadata = {
            "atlas_size": list(sizes[0]),
            "padding": self.padding,
            "sprite_count": len(packed_sprites),
            "pages": [{"size": list(size)} for size in sizes],
            "regions": {
                sprite.name: {
                    "x": sprite.x,
                    "y": sprite.y,
                    "width": sprite.width,
                    "height": sprite.height,
                    "original_size": list(sprite.original_size),
                    "offset": list(sprite.offset),
                    "page": sprite.page,
                }
                for sprite in sorted(packed_sprites, key=lambda s: s.name)
            },
        }

        return pages, metadata

    def _page_size(self, sprites: list[PackedSprite], page: int) -> tuple[int, int]:
        """Return the size page `page` is written at, given `fit`."""
        if self.fit == "fixed":
            return self.atlas_size, self.atlas_height
        on_page = [sprite for sprite in sprites if sprite.page == page]
        width = max(sprite.x + sprite.width + self.padding for sprite in on_page)
        height = max(sprite.y + sprite.height + self.padding for sprite in on_page)
        if self.fit == "pot":
            width = min(_power_of_two(width), self.atlas_size)
            height = min(_power_of_two(height), self.atlas_height)
        return width, height

    def generate(
        self,
        input_path: Path,
        output_path: Path,
        metadata_path: Path | None = None,
    ) -> None:
        """Generate atlas from input directory.

        A second page and later are written beside `output_path` as
        `<name>_1.png`, `<name>_2.png` and so on, and need `metadata_path`,
        since only the metadata says which page holds a sprite.

        Args:
            input_path (Path): Directory containing sprite images.
            output_path (Path): Path for output atlas image.
            metadata_path (Optional[Path]): Path for JSON metadata file.

        Raises:
            ValueError: If the sprites need several pages and there is no
                `metadata_path`, or `pack_pages()` refuses them.
        """
        # Never re-ingest our own output when it is written back into the
        # input directory (a common -i/-o overlap), including the extra pages
        # a previous run wrote.
        previous_pages = _previous_pages(output_path, metadata_path)
        exclude = {output_path.resolve(), *(p.resolve() for p in previous_pages)}
        if metadata_path is not None:
            exclude.add(metadata_path.resolve())

        print(f"Loading images from: {input_path}")
        images = self.load_images(input_path, exclude=exclude)
        print(f"Loaded {len(images)} images")

        print("Packing atlas...")
        if metadata_path is None:
            atlas_image, metadata = self.pack(images)
            page_images = [atlas_image]
        else:
            page_images, metadata = self.pack_pages(images)

        page_paths = [output_path] + [
            output_path.with_name(f"{output_path.stem}_{index}.png")
            for index in range(1, len(page_images))
        ]
        for entry, path in zip(metadata["pages"], page_paths, strict=True):
            entry["image"] = path.name

        # Create output directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)

        for image, path in zip(page_images, page_paths, strict=True):
            print(f"Saving atlas page to: {path}")
            image.save(path, "PNG")
        # A page the previous run wrote and this one did not would be
        # mistaken for a sprite by the next run.
        for stale in set(previous_pages) - set(page_paths):
            stale.unlink(missing_ok=True)

        # Save metadata if requested
        if metadata_path:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            print(f"Saving metadata to: {metadata_path}")
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

        print(
            f"Atlas generation complete: {metadata['sprite_count']} sprites "
            f"packed on {len(page_images)} page(s)"
        )


def _trimmed(image: Image.Image) -> tuple[Image.Image, tuple[int, int]]:
    """Cut `image`'s fully transparent border off, keeping where it was.

    A wholly transparent image keeps one transparent pixel, so it still has
    a region to look up.
    """
    box = image.getchannel("A").getbbox()
    if box is None:
        return image.crop((0, 0, 1, 1)), (0, 0)
    return image.crop(box), (box[0], box[1])


def _power_of_two(value: int) -> int:
    return 1 << max(value - 1, 0).bit_length()


def _previous_pages(output_path: Path, metadata_path: Path | None) -> list[Path]:
    """Return the extra pages an earlier run recorded in `metadata_path`."""
    if metadata_path is None or not metadata_path.is_file():
        return []
    try:
        previous = json.loads(metadata_path.read_text(encoding="utf-8"))
        entries = previous.get("pages", [])[1:]
        names = [entry["image"] for entry in entries]
    except (ValueError, TypeError, KeyError, AttributeError):
        return []
    return [
        output_path.with_name(name)
        for name in names
        if isinstance(name, str) and name == Path(name).name
    ]


def _parse_size(
    _ctx: click.Context, _param: click.Parameter, value: str
) -> tuple[int, int]:
    width, _, height = value.lower().partition("x")
    try:
        size = (int(width), int(height or width))
    except ValueError:
        raise click.BadParameter(
            f"expected a size such as 2048 or 2048x1024, not {value!r}"
        ) from None
    if min(size) <= 0:
        raise click.BadParameter(f"a page must be at least 1x1, not {value!r}")
    return size


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
    default="2048",
    callback=_parse_size,
    help="Largest page: 2048 for a square, or 2048x1024 (default: 2048)",
)
@click.option(
    "-p",
    "--padding",
    type=int,
    default=2,
    help="Padding between sprites (default: 2)",
)
@click.option(
    "--trim/--no-trim",
    default=False,
    help="Cut each sprite's transparent border off, recording the offset",
)
@click.option(
    "--fit",
    type=click.Choice(FITS),
    default="fixed",
    help="Page size: the full --size, tight to what it holds, or tight "
    "rounded up to a power of two (default: fixed)",
)
def atlas(
    input_dir: Path,
    output: Path,
    metadata: Path | None,
    size: tuple[int, int],
    padding: int,
    trim: bool,
    fit: str,
) -> None:  # noqa: D301  (\b is Click's no-wrap marker; r""" would defeat it)
    """Generate a sprite atlas from multiple images.

    Pack sprites from INPUT directory into a texture atlas using a
    shelf-packing algorithm. Sprites that overflow a page go on the next,
    which needs metadata (-m) to say which page holds each sprite.

    \b
    Examples:
      # Basic usage
      pyguara atlas -i assets/sprites/ -o atlas.png
      # With metadata
      pyguara atlas -i assets/sprites/ -o atlas.png -m atlas.json
      # Custom size and padding
      pyguara atlas -i assets/sprites/ -o atlas.png -s 4096 -p 4
      # Trimmed, on 1024x512 pages cropped to a power of two
      pyguara atlas -i sprites/ -o atlas.png -m atlas.json -s 1024x512 \\
        --trim --fit pot
    """
    try:
        generator = AtlasGenerator(
            atlas_size=size[0],
            padding=padding,
            atlas_height=size[1],
            trim=trim,
            fit=fit,
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

    Delegates to the :func:`atlas` Click command, so the module-level
    invocation and ``pyguara atlas`` share one option surface.
    """
    atlas.main(prog_name="pyguara.cli.atlas_generator")


if __name__ == "__main__":
    main()
