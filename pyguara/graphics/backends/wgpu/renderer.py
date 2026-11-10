"""`IRenderer` on wgpu: the world renderer.

Every call here pushes one primitive into the native frame. Nothing is
drawn until the window presents.

**It is held to the pygame renderer, pixel for pixel where that is
possible.** The pygame backend is what games run on today, so this one
puts a rectangle on the same pixels, a line through the same pixel
centres, and text at the same integer position. Where the two cannot
agree exactly -- the edge of a circle, the ends of a thick line -- the
difference is bounded by `tests/integration/test_wgpu_pixels.py`.

Coordinates: pygame names a pixel by its top-left corner and draws shapes
through pixel *indices*. The GPU rasterises through pixel *centres*. So a
circle or a line whose pygame coordinates are `(x, y)` is drawn here about
`(x + 0.5, y + 0.5)`.
"""

from __future__ import annotations

import math

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.backends.surface_texture import as_surface
from pyguara.graphics.backends.wgpu.frame import CIRCLE_SHRINK, GpuFrame, line_quad
from pyguara.graphics.types import RenderBatch
from pyguara.resources.types import Texture


class WgpuRenderer:
    """Renderer backend that draws through the native wgpu frame."""

    def __init__(self, frame: GpuFrame) -> None:
        """Draw into a frame.

        Args:
            frame: The frame shared with the window and the UI renderer.
        """
        self._frame = frame
        self._gpu = frame.gpu

    @property
    def width(self) -> int:
        """Get the width of the render target."""
        return int(self._gpu.width)

    @property
    def height(self) -> int:
        """Get the height of the render target."""
        return int(self._gpu.height)

    def begin_frame(self) -> None:
        """Prepare for a new frame. Nothing to do: the window owns the frame."""

    def end_frame(self) -> None:
        """Finish a frame. Nothing to do: the window presents it."""

    def clear(self, color: Color) -> None:
        """Clear the target, or the current viewport, with a colour."""
        self._gpu.clear(color.r, color.g, color.b, 255)

    def set_viewport(self, viewport: Rect) -> None:
        """Restrict drawing to a region."""
        self._gpu.set_scissor(
            int(viewport.x), int(viewport.y), int(viewport.width), int(viewport.height)
        )

    def reset_viewport(self) -> None:
        """Draw to the whole target again."""
        self._gpu.clear_scissor()

    def draw_rect(self, rect: Rect, color: Color, width: int = 0) -> None:
        """Draw a rectangle primitive, filled or outlined."""
        if color.a == 0:
            return
        if width > 0:
            self._gpu.rect_outline(
                rect.x, rect.y, rect.width, rect.height, width,
                color.r, color.g, color.b, color.a,
            )  # fmt: skip
        else:
            self._gpu.rect(
                rect.x, rect.y, rect.width, rect.height,
                color.r, color.g, color.b, color.a,
            )  # fmt: skip

    def draw_circle(
        self, center: Vector2, radius: float, color: Color, width: int = 0
    ) -> None:
        """Draw a circle primitive, filled or as a ring."""
        if color.a == 0:
            return
        whole = int(radius)
        if whole <= 0:
            return
        self._gpu.circle(
            int(center.x), int(center.y),
            whole - CIRCLE_SHRINK,
            whole - width - CIRCLE_SHRINK if 0 < width < whole else 0,
            color.r, color.g, color.b, color.a,
        )  # fmt: skip

    def draw_line(
        self, start: Vector2, end: Vector2, color: Color, width: int = 1
    ) -> None:
        """Draw a line primitive."""
        if color.a == 0 or width <= 0:
            return
        from_x, from_y, to_x, to_y, thickness = line_quad(
            start.x, start.y, end.x, end.y, width
        )
        self._gpu.line(
            from_x, from_y, to_x, to_y, thickness,
            color.r, color.g, color.b, color.a,
        )  # fmt: skip

    def draw_text(
        self, text: str, position: Vector2, color: Color, size: int = 16
    ) -> None:
        """Draw a text string, in screen space (see `IRenderer.draw_text`)."""
        if not text or color.a == 0:
            return
        run = self._frame.text(text, size)
        if run is None:
            return
        texture, width, height = run
        self._gpu.quad(
            texture,
            int(position.x) + width / 2, int(position.y) + height / 2,
            width / 2, height / 2,
            0, 0, width, height, 0.0,
            color.r, color.g, color.b, color.a,
        )  # fmt: skip

    def draw_texture(
        self,
        texture: Texture,
        destination: Vector2,
        rotation: float = 0.0,
        scale: Vector2 = Vector2(1, 1),
    ) -> None:
        """Draw a single texture, centred on `destination`.

        Honours `rotation` in degrees and `scale`, and treats a negative
        scale on either axis as a flip, as `IRenderer.draw_texture` says.
        """
        surface = as_surface(texture)
        if surface is None:
            return
        width, height = surface.get_size()
        # Rounded to whole pixels and never below one, as the pygame
        # backend scales, so a sprite is the same size on both.
        half_width = max(1, round(width * abs(scale.x))) / 2
        half_height = max(1, round(height * abs(scale.y))) / 2
        self._gpu.quad(
            self._frame.surface(surface),
            int(destination.x), int(destination.y),
            -half_width if scale.x < 0 else half_width,
            -half_height if scale.y < 0 else half_height,
            0, 0, width, height, rotation,
            255, 255, 255, 255,
        )  # fmt: skip

    def render_batch(self, batch: RenderBatch) -> None:
        """Draw many instances of one texture.

        Places sprites as the pygame backend does: a destination is the
        top-left corner of the sprite's box, and a rotated sprite's box is
        the one that bounds it after turning.
        """
        surface = as_surface(batch.texture)
        if surface is None:
            return
        texture = self._frame.surface(surface)
        full_width, full_height = surface.get_size()
        regions = batch.source_rects if batch.source_rects_enabled else ()
        transforms = batch.transforms_enabled
        tinted = batch.colors_enabled
        quad = self._gpu.quad

        for index, (x, y) in enumerate(batch.destinations):
            region = regions[index] if regions else None
            if region is None:
                source_x, source_y = 0, 0
                width, height = full_width, full_height
            else:
                source_x, source_y = int(region.x), int(region.y)
                width, height = int(region.width), int(region.height)
            turn = 0.0
            box_width, box_height = float(width), float(height)
            drawn_width, drawn_height = float(width), float(height)
            if transforms:
                if index < len(batch.rotations):
                    turn = batch.rotations[index]
                if index < len(batch.scales):
                    scale_x, scale_y = batch.scales[index]
                    drawn_width = float(int(width * scale_x))
                    drawn_height = float(int(height * scale_y))
                if turn != 0.0:
                    radians = math.radians(turn)
                    cos, sin = abs(math.cos(radians)), abs(math.sin(radians))
                    # pygame turns first and scales the turned box; the
                    # box that bounds the result is what `dest` anchors.
                    box_width = (width * cos + height * sin) * (drawn_width / width)
                    box_height = (width * sin + height * cos) * (drawn_height / height)
                else:
                    box_width, box_height = drawn_width, drawn_height
            red, green, blue, alpha = 255, 255, 255, 255
            if tinted and index < len(batch.colors):
                red, green, blue, alpha = batch.colors[index]
            quad(
                texture,
                x + box_width / 2, y + box_height / 2,
                drawn_width / 2, drawn_height / 2,
                source_x, source_y, width, height, turn,
                red, green, blue, alpha,
            )  # fmt: skip

    def resize(self, width: int, height: int) -> None:
        """Adopt a new target size.

        Args:
            width: The new width in pixels.
            height: The new height in pixels.
        """
        if (width, height) != (self.width, self.height):
            self._gpu.resize(width, height)

    def present(self) -> None:
        """Present the frame. Nothing to do: the window presents it."""
