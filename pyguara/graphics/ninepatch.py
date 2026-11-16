"""Nine-patch sprite support for scalable UI elements.

Nine-patch sprites divide an image into 9 sections (corners, edges, center)
that can be scaled independently while preserving corner details.

Nothing here imports a backend or the resource manager. The caller
hands over a texture it has already resolved, as `ui.components.Image`
takes one.
"""

from dataclasses import dataclass
from typing import Any

from pyguara.common.types import Color, Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.log import get_logger

logger = get_logger(__name__)


@dataclass
class NinePatchMetrics:
    """Defines the 9-patch division metrics.

    Attributes:
        left: Left edge width in pixels
        right: Right edge width in pixels
        top: Top edge height in pixels
        bottom: Bottom edge height in pixels
    """

    left: int
    right: int
    top: int
    bottom: int

    def __post_init__(self) -> None:
        """Reject negative edges.

        A negative edge produces negative-width source and destination rects,
        which reach the renderer as geometry rather than as an error.

        Raises:
            ValueError: If any edge is negative.
        """
        negative = {
            name: value
            for name, value in (
                ("left", self.left),
                ("right", self.right),
                ("top", self.top),
                ("bottom", self.bottom),
            )
            if value < 0
        }
        if negative:
            raise ValueError(f"Nine-patch edges cannot be negative: {negative}.")

    @classmethod
    def uniform(cls, size: int) -> "NinePatchMetrics":
        """Create uniform metrics (all edges same size).

        Args:
            size: Size in pixels for all edges

        Returns:
            NinePatchMetrics with all edges set to size
        """
        return cls(left=size, right=size, top=size, bottom=size)

    @classmethod
    def symmetric(cls, horizontal: int, vertical: int) -> "NinePatchMetrics":
        """Create symmetric metrics (left/right same, top/bottom same).

        Args:
            horizontal: Size for left and right edges
            vertical: Size for top and bottom edges

        Returns:
            NinePatchMetrics with symmetric edges
        """
        return cls(left=horizontal, right=horizontal, top=vertical, bottom=vertical)


@dataclass
class NinePatchSprite:
    """Nine-patch sprite component for scalable UI rendering.

    A nine-patch sprite divides a texture into 9 sections:
    - 4 corners (fixed size, never stretched)
    - 4 edges (stretched in one direction)
    - 1 center (stretched in both directions)

    This allows UI elements like buttons and panels to scale properly
    without distorting corners.

    Attributes:
        texture_path: Path to the texture atlas/sprite image
        source_rect: Source rectangle in the texture (entire image if None)
        metrics: Nine-patch division metrics
        min_size: Minimum render size (prevents over-shrinking)
    """

    texture_path: str
    metrics: NinePatchMetrics
    source_rect: Rect | None = None
    min_size: Vector2 | None = None

    def get_min_size(self) -> Vector2:
        """Get the minimum size this nine-patch can be rendered at.

        Returns:
            Minimum size vector (sum of edges in each direction)
        """
        if self.min_size:
            return self.min_size

        # Calculate from metrics
        min_width = self.metrics.left + self.metrics.right
        min_height = self.metrics.top + self.metrics.bottom
        return Vector2(min_width, min_height)

    def get_patch_rects(self, source_width: int, source_height: int) -> list[Rect]:
        """Calculate source rectangles for each patch.

        The rects are in texture coordinates. When `source_rect` says this
        nine-patch lives inside a larger atlas, every rect is offset by that
        region's origin.

        Args:
            source_width: Width of the source region. Ignored when
                `source_rect` is set, which carries its own extent.
            source_height: Height of the source region, likewise.

        Returns:
            List of 9 Rect objects for source positions
            in order: TL, T, TR, L, C, R, BL, B, BR

        Raises:
            ValueError: If the edges do not fit inside the source, which
                would leave the centre with negative extent.
        """
        m = self.metrics
        if self.source_rect is not None:
            ox, oy = self.source_rect.x, self.source_rect.y
            sw, sh = self.source_rect.width, self.source_rect.height
        else:
            ox, oy = 0, 0
            sw, sh = source_width, source_height

        if m.left + m.right > sw or m.top + m.bottom > sh:
            raise ValueError(
                f"Nine-patch edges do not fit the source texture: edges "
                f"{m.left}+{m.right} wide and {m.top}+{m.bottom} tall against a "
                f"{sw}x{sh} texture. The centre patch would have negative extent."
            )

        # Source rectangles (from texture)
        src_rects = [
            # Top-Left corner
            Rect(ox, oy, m.left, m.top),
            # Top edge
            Rect(ox + m.left, oy, sw - m.left - m.right, m.top),
            # Top-Right corner
            Rect(ox + sw - m.right, oy, m.right, m.top),
            # Left edge
            Rect(ox, oy + m.top, m.left, sh - m.top - m.bottom),
            # Center
            Rect(
                ox + m.left,
                oy + m.top,
                sw - m.left - m.right,
                sh - m.top - m.bottom,
            ),
            # Right edge
            Rect(ox + sw - m.right, oy + m.top, m.right, sh - m.top - m.bottom),
            # Bottom-Left corner
            Rect(ox, oy + sh - m.bottom, m.left, m.bottom),
            # Bottom edge
            Rect(ox + m.left, oy + sh - m.bottom, sw - m.left - m.right, m.bottom),
            # Bottom-Right corner
            Rect(ox + sw - m.right, oy + sh - m.bottom, m.right, m.bottom),
        ]

        return src_rects

    def get_dest_rects(self, x: int, y: int, width: int, height: int) -> list[Rect]:
        """Calculate destination rectangles for rendering.

        Args:
            x: X position to render at
            y: Y position to render at
            width: Width to render at (must be >= min_width)
            height: Height to render at (must be >= min_height)

        Returns:
            List of 9 Rect objects for destination positions
            in order: TL, T, TR, L, C, R, BL, B, BR
        """
        m = self.metrics

        # Ensure we don't render smaller than minimum
        min_size = self.get_min_size()
        width = max(width, int(min_size.x))
        height = max(height, int(min_size.y))

        # Calculate stretched dimensions
        center_width = width - m.left - m.right
        center_height = height - m.top - m.bottom

        # Destination rectangles (where to draw)
        dest_rects = [
            # Top-Left corner
            Rect(x, y, m.left, m.top),
            # Top edge (stretch horizontally)
            Rect(x + m.left, y, center_width, m.top),
            # Top-Right corner
            Rect(x + width - m.right, y, m.right, m.top),
            # Left edge (stretch vertically)
            Rect(x, y + m.top, m.left, center_height),
            # Center (stretch both directions)
            Rect(x + m.left, y + m.top, center_width, center_height),
            # Right edge (stretch vertically)
            Rect(x + width - m.right, y + m.top, m.right, center_height),
            # Bottom-Left corner
            Rect(x, y + height - m.bottom, m.left, m.bottom),
            # Bottom edge (stretch horizontally)
            Rect(x + m.left, y + height - m.bottom, center_width, m.bottom),
            # Bottom-Right corner
            Rect(x + width - m.right, y + height - m.bottom, m.right, m.bottom),
        ]

        return dest_rects


def texture_size(texture: Any) -> tuple[int, int]:
    """Report a texture's pixel size, whichever shape of texture it is.

    The two halves of the engine wrap a texture differently and both
    reach a `UIRenderer`: the world side passes a `resources.Texture`,
    with `width` and `height` properties, while the UI side's
    `draw_texture` takes `Any` and the real backends require the raw
    `pygame.Surface`, which answers `get_width()`. `ui.components.Image`
    is handed the latter. Rather than pick one and make the other a type
    error far from here, ask for either -- and say so, since a caller
    reading `texture: Any` has no way to know what is acceptable.

    Args:
        texture: A `resources.Texture`, or a backend surface.

    Returns:
        `(width, height)` in pixels.

    Raises:
        TypeError: If it is neither. Raised here, at the boundary, naming
            what was passed -- the alternative is an `AttributeError`
            from inside a slice loop that has already drawn four of nine
            patches.
    """
    width = getattr(texture, "width", None)
    if isinstance(width, int):
        return (width, int(texture.height))
    getter = getattr(texture, "get_width", None)
    if callable(getter):
        return (int(getter()), int(texture.get_height()))
    raise TypeError(
        f"A nine-patch needs its texture's size, and {type(texture).__name__} "
        f"has neither a `width` property nor a `get_width()` method. Pass a "
        f"pyguara.resources.Texture or the backend surface a UIRenderer draws."
    )


def render_ninepatch(
    renderer: UIRenderer,
    ninepatch: NinePatchSprite,
    texture: Any,
    x: int,
    y: int,
    width: int,
    height: int,
    color: Color | None = None,
) -> int:
    """Render a nine-patch sprite: nine draws, one per slice.

    Corners keep their pixel size at any destination size, edges stretch
    along one axis and the centre stretches along both.

    A slice with no extent is skipped. `metrics.left == 0` makes three of
    the nine destination rects zero-width, and an edge as thick as half
    the destination leaves the centre empty; both are ordinary.

    Args:
        renderer: UI renderer to draw with.
        ninepatch: Nine-patch sprite to render.
        texture: The resolved texture, as `UIRenderer.draw_texture` takes
            it. Its size is read through `texture_size`.
        x: X position to render at.
        y: Y position to render at.
        width: Width to render at. Clamped up to the minimum by
            `get_dest_rects`, so the corners never overlap.
        height: Height to render at, likewise.
        color: Optional tint, passed through to every slice.

    Returns:
        How many slices were drawn, 0 to 9.
    """
    source_width, source_height = texture_size(texture)
    sources = ninepatch.get_patch_rects(source_width, source_height)
    destinations = ninepatch.get_dest_rects(x, y, width, height)

    drawn = 0
    for source, destination in zip(sources, destinations, strict=True):
        if source.width <= 0 or source.height <= 0:
            continue
        if destination.width <= 0 or destination.height <= 0:
            continue
        renderer.draw_texture(texture, destination, color, source)
        drawn += 1
    return drawn
