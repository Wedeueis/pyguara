"""Nine-patch sprite support for scalable UI elements.

Nine-patch sprites divide an image into 9 sections (corners, edges, center)
that can be scaled independently while preserving corner details.
"""

from dataclasses import dataclass
from typing import Optional

from pyguara.common.types import Vector2, Rect
from pyguara.graphics.protocols import UIRenderer


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
    source_rect: Optional[Rect] = None
    min_size: Optional[Vector2] = None

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

        Args:
            source_width: Width of the source texture
            source_height: Height of the source texture

        Returns:
            List of 9 Rect objects for source positions
            in order: TL, T, TR, L, C, R, BL, B, BR
        """
        m = self.metrics
        sw = source_width
        sh = source_height

        # Source rectangles (from texture)
        src_rects = [
            # Top-Left corner
            Rect(0, 0, m.left, m.top),
            # Top edge
            Rect(m.left, 0, sw - m.left - m.right, m.top),
            # Top-Right corner
            Rect(sw - m.right, 0, m.right, m.top),
            # Left edge
            Rect(0, m.top, m.left, sh - m.top - m.bottom),
            # Center
            Rect(m.left, m.top, sw - m.left - m.right, sh - m.top - m.bottom),
            # Right edge
            Rect(sw - m.right, m.top, m.right, sh - m.top - m.bottom),
            # Bottom-Left corner
            Rect(0, sh - m.bottom, m.left, m.bottom),
            # Bottom edge
            Rect(m.left, sh - m.bottom, sw - m.left - m.right, m.bottom),
            # Bottom-Right corner
            Rect(sw - m.right, sh - m.bottom, m.right, m.bottom),
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


def render_ninepatch(
    renderer: UIRenderer,
    ninepatch: NinePatchSprite,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    """Render a nine-patch sprite.

    Args:
        renderer: UI renderer to draw with
        ninepatch: Nine-patch sprite to render
        x: X position to render at
        y: Y position to render at
        width: Width to render at
        height: Height to render at
    """
    # Get source rect or use full texture
    # Note: In a real implementation, we'd need to query the texture size
    # For now, assume the source_rect provides the info or we'd need
    # a texture manager to query dimensions

    # This is a placeholder - actual implementation would need texture loading
    # to get source dimensions. For now, we'll document the interface.
    pass
