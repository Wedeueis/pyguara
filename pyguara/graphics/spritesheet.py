"""
Utilities for handling sprite sheet assets.

This module provides the logic to slice a single large texture into multiple
smaller sub-textures (frames) that can be played back by the animation system.

The implementation is backend-agnostic, using Pillow for image manipulation
and a TextureFactory protocol for creating backend-specific textures.
"""

from PIL import Image

from pyguara.graphics.components.animation import AnimationClip, PlaybackMode
from pyguara.graphics.protocols import TextureFactory
from pyguara.resources.meta import SpritesheetMeta
from pyguara.resources.types import Texture


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
        self._frames: list[Texture] = []

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

    def slice_from_meta(self, meta: SpritesheetMeta, count: int = 0) -> list[Texture]:
        """Slice the sheet using a SpritesheetMeta sidecar's grid settings.

        Reads ``frame_width``, ``frame_height``, ``margin`` and ``spacing``
        from the meta. ``filter`` is a texture-import setting and is not
        applied here.

        Args:
            meta: The spritesheet import settings.
            count: Maximum number of frames to extract (0 = all that fit).

        Returns:
            List of Texture objects, one per extracted frame.
        """
        return self.slice_grid(
            meta.frame_width,
            meta.frame_height,
            count=count,
            margin=meta.margin,
            spacing=meta.spacing,
        )

    def slice_grid(
        self,
        frame_width: int,
        frame_height: int,
        count: int = 0,
        margin: int = 0,
        spacing: int = 0,
    ) -> list[Texture]:
        """Slice the sprite sheet into a grid of equal-sized frames.

        Frames are extracted left-to-right, top-to-bottom (row-major order).

        Args:
            frame_width: Width of a single frame in pixels.
            frame_height: Height of a single frame in pixels.
            count: Maximum number of frames to extract. If 0, extracts all
                   frames that fit in the grid.
            margin: Blank border in pixels between the sheet edge and the
                    first row/column of frames.
            spacing: Blank gutter in pixels between adjacent frames.

        Returns:
            List of Texture objects, one for each extracted frame.
        """
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("frame_width and frame_height must be positive")

        # Calculate grid dimensions, accounting for margin and inter-frame
        # spacing: n frames occupy n*frame + (n-1)*spacing, plus 2*margin.
        stride_x = frame_width + spacing
        stride_y = frame_height + spacing
        cols = max(0, (self._image.width - 2 * margin + spacing) // stride_x)
        rows = max(0, (self._image.height - 2 * margin + spacing) // stride_y)

        total_possible = cols * rows
        frames_to_load = count if count > 0 else total_possible

        self._frames = []
        loaded = 0

        for y in range(rows):
            for x in range(cols):
                if loaded >= frames_to_load:
                    break

                # Calculate the crop box (left, upper, right, lower)
                left = margin + x * stride_x
                upper = margin + y * stride_y
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

    def slice_regions(self, regions: list[tuple[int, int, int, int]]) -> list[Texture]:
        """Slice specific regions from the sprite sheet.

        Useful for sprite sheets with irregular frame sizes or layouts.

        Args:
            regions: List of (x, y, width, height) tuples defining each frame.

        Returns:
            List of Texture objects, one for each specified region.
        """
        textures: list[Texture] = []

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

    def clip(
        self,
        name: str,
        frame_width: int,
        frame_height: int,
        row: int = 0,
        count: int = 0,
        fps: float = 10.0,
        *,
        loop: bool = True,
        mode: PlaybackMode | None = None,
        loop_count: int = 1,
        frame_events: dict[int, tuple[str, ...]] | None = None,
        margin: int = 0,
        spacing: int = 0,
    ) -> AnimationClip:
        """Build an `AnimationClip` from one row of the grid.

        `slice_grid()` returns a flat row-major list, so building a clip
        meant slicing `frames[8:16]` by hand and getting the arithmetic
        right every time -- friction rather than architecture, and the one
        place a sprite sheet's layout leaks into game code.

        A row, not an arbitrary span, because that is how sprite sheets are
        actually laid out: one action per row. Use `slice_grid()` plus a
        slice for anything stranger.

        Args:
            name: The clip's name, e.g. `"walk_down"`.
            frame_width: Width of a single frame in pixels.
            frame_height: Height of a single frame in pixels.
            row: 0-based row index.
            count: How many frames to take from that row. 0 takes the
                whole row.
            fps: The clip's frame rate.
            loop: Whether the clip loops. Ignored if `mode` is given.
            mode: Explicit `PlaybackMode`, for ping-pong or play-N-times.
            loop_count: How many loops `LOOP_TIMES` runs.
            frame_events: Frame index to event names, as `AnimationClip`
                takes them. Indices are relative to this clip, not to the
                sheet -- frame 0 is the first frame of the row.
            margin: Blank border between the sheet edge and the grid.
            spacing: Blank gutter between adjacent frames.

        Returns:
            The clip, with its frames already sliced.

        Raises:
            ValueError: If the row is out of range, or the requested count
                exceeds what the row holds. Both mean the caller's idea of
                the sheet disagrees with the sheet, and a clip quietly
                short of frames animates wrongly rather than visibly
                failing.
        """
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("frame_width and frame_height must be positive")
        if row < 0:
            raise ValueError(f"row must not be negative, got {row}")

        stride_x = frame_width + spacing
        stride_y = frame_height + spacing
        columns = max(0, (self._image.width - 2 * margin + spacing) // stride_x)
        rows = max(0, (self._image.height - 2 * margin + spacing) // stride_y)

        if row >= rows:
            raise ValueError(
                f"Row {row} is outside the sheet: a {frame_width}x"
                f"{frame_height} grid of {self._path} has {rows} row(s)."
            )

        wanted = columns if count <= 0 else count
        if wanted > columns:
            raise ValueError(
                f"Asked for {count} frames from row {row}, but a "
                f"{frame_width}x{frame_height} grid of {self._path} has "
                f"{columns} column(s)."
            )

        regions = [
            (
                margin + column * stride_x,
                margin + row * stride_y,
                frame_width,
                frame_height,
            )
            for column in range(wanted)
        ]

        return AnimationClip(
            name=name,
            frames=self.slice_regions(regions),
            frame_rate=fps,
            loop=loop,
            mode=mode,
            loop_count=loop_count,
            frame_events=frame_events or {},
        )

    @property
    def frames(self) -> list[Texture]:
        """Get the list of previously sliced frames."""
        return self._frames
