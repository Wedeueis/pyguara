"""`UIRenderer` on wgpu.

The UI is drawn into the same native frame as the world, after it, as
instanced quads. That is the difference from the retired ModernGL UI renderer,
which drew onto a CPU surface and uploaded the whole of it every frame:
about 12 ms at 1080p (issue #334), paid whether the HUD is one label or a
full menu. Here a label costs one quad.
"""

from __future__ import annotations

from typing import Any

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.backends.clipping import ClipStack
from pyguara.graphics.backends.wgpu.frame import CIRCLE_SHRINK, GpuFrame, line_quad
from pyguara.graphics.backends.wgpu.polygon import rasterise_polygon
from pyguara.log import get_logger

logger = get_logger(__name__)


class WgpuUIRenderer:
    """Concrete `UIRenderer` drawing through the native wgpu frame."""

    def __init__(self, frame: GpuFrame) -> None:
        """Draw into a frame.

        Args:
            frame: The frame shared with the window and the world renderer.
        """
        self._frame = frame
        self._gpu = frame.gpu
        self._clips = ClipStack()
        self._warned_about_clips = False

    def draw_rect(
        self, rect: Rect, color: Color, width: int = 0, border_radius: int = 0
    ) -> None:
        """Draw a filled or outlined rectangle, optionally with round corners."""
        if color.a == 0 or rect.width <= 0 or rect.height <= 0:
            return
        if border_radius > 0:
            self._gpu.rounded_rect(
                rect.x, rect.y, rect.width, rect.height, border_radius, width,
                color.r, color.g, color.b, color.a,
            )  # fmt: skip
        elif width > 0:
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
        """Draw a filled or outlined circle."""
        whole = int(radius)
        if color.a == 0 or whole <= 0:
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
        """Draw a line."""
        if color.a == 0 or width <= 0:
            return
        from_x, from_y, to_x, to_y, thickness = line_quad(
            start.x, start.y, end.x, end.y, width
        )
        self._gpu.line(
            from_x, from_y, to_x, to_y, thickness,
            color.r, color.g, color.b, color.a,
        )  # fmt: skip

    def draw_polygon(
        self, points: list[tuple[int, int]], color: Color, width: int = 0
    ) -> None:
        """Draw a filled or outlined polygon.

        The native pipeline draws quads, and an arbitrary polygon is not
        one. So this rasterises it on the CPU (`polygon.py`, pygame's own
        rules) into a mask the size of its bounding box and draws that once. Polygons are rare in a UI
        -- a dropdown's arrow, a slider's notch -- and small.
        """
        if color.a == 0 or len(points) < 3:
            return
        pixels, left, top, box_width, box_height = rasterise_polygon(points, width)
        self._gpu.quad(
            self._frame.once_rgba(pixels, box_width, box_height),
            left + box_width / 2, top + box_height / 2,
            box_width / 2, box_height / 2,
            0, 0, box_width, box_height, 0.0,
            color.r, color.g, color.b, color.a,
        )  # fmt: skip

    def draw_text(
        self,
        text: str,
        position: Vector2,
        color: Color,
        size: int = 16,
        *,
        bold: bool = False,
        italic: bool = False,
    ) -> None:
        """Draw a text string."""
        if not text or color.a == 0:
            return
        run = self._frame.text(text, size, bold, italic)
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
        texture: Any,
        rect: Rect,
        color: Color | None = None,
        source_rect: Rect | None = None,
    ) -> None:
        """Draw an image, or the `source_rect` region of it, scaled into `rect`."""
        if rect.width <= 0 or rect.height <= 0:
            return
        image = self._frame.image(texture)
        if image is None:
            return
        uploaded, width, height = image
        whole = Rect(0, 0, width, height)
        region = whole if source_rect is None else source_rect.clip(whole)
        if region.width <= 0 or region.height <= 0:
            return
        red, green, blue = (color.r, color.g, color.b) if color else (255, 255, 255)
        self._gpu.quad(
            uploaded,
            rect.x + rect.width / 2, rect.y + rect.height / 2,
            rect.width / 2, rect.height / 2,
            region.x, region.y, region.width, region.height, 0.0,
            red, green, blue, 255,
        )  # fmt: skip

    def get_text_size(
        self, text: str, size: int, *, bold: bool = False, italic: bool = False
    ) -> tuple[int, int]:
        """Calculate the width and height of a string."""
        width, height = self._frame.font(size, bold, italic).size(text)
        return (int(width), int(height))

    def get_line_height(self, size: int) -> int:
        """Return the font's own line advance, leading included."""
        return int(self._frame.font(size).line_height)

    def push_clip(self, rect: Rect) -> None:
        """Restrict drawing to `rect`, intersected with any active clip."""
        self._apply_clip(self._clips.push(rect))

    def pop_clip(self) -> None:
        """Undo the most recent `push_clip()`."""
        self._apply_clip(self._clips.pop())

    def _apply_clip(self, rect: Rect | None) -> None:
        if rect is None:
            self._gpu.clear_scissor()
        else:
            self._gpu.set_scissor(rect.x, rect.y, rect.width, rect.height)

    def resize(self, width: int, height: int) -> None:
        """Nothing to store: the UI draws into the world's own target."""

    def present(self) -> None:
        """Finish the UI pass, dropping any clip a widget failed to pop."""
        if self._clips.depth:
            if not self._warned_about_clips:
                self._warned_about_clips = True
                logger.warning(
                    f"{self._clips.depth} UI clip region(s) were pushed and never "
                    f"popped. The clip is reset at the end of each frame; pair "
                    f"every push_clip() with a pop_clip(). Reported once."
                )
            self._apply_clip(self._clips.clear())
