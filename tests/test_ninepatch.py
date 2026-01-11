"""Tests for nine-patch sprite system."""

from pyguara.common.types import Vector2, Rect
from pyguara.graphics.ninepatch import (
    NinePatchMetrics,
    NinePatchSprite,
)


class TestNinePatchMetrics:
    """Test nine-patch metrics creation."""

    def test_uniform_metrics(self):
        """Uniform metrics should set all edges to same size."""
        metrics = NinePatchMetrics.uniform(10)

        assert metrics.left == 10
        assert metrics.right == 10
        assert metrics.top == 10
        assert metrics.bottom == 10

    def test_symmetric_metrics(self):
        """Symmetric metrics should set horizontal and vertical pairs."""
        metrics = NinePatchMetrics.symmetric(horizontal=15, vertical=10)

        assert metrics.left == 15
        assert metrics.right == 15
        assert metrics.top == 10
        assert metrics.bottom == 10

    def test_custom_metrics(self):
        """Custom metrics should allow individual edge sizes."""
        metrics = NinePatchMetrics(left=5, right=10, top=15, bottom=20)

        assert metrics.left == 5
        assert metrics.right == 10
        assert metrics.top == 15
        assert metrics.bottom == 20


class TestNinePatchSprite:
    """Test nine-patch sprite functionality."""

    def test_sprite_creation(self):
        """Nine-patch sprite should be created with basic properties."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        assert sprite.texture_path == "button.png"
        assert sprite.metrics == metrics
        assert sprite.source_rect is None
        assert sprite.min_size is None

    def test_get_min_size_from_metrics(self):
        """Minimum size should be calculated from metrics if not specified."""
        metrics = NinePatchMetrics(left=10, right=15, top=8, bottom=12)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        min_size = sprite.get_min_size()

        assert min_size.x == 25  # 10 + 15
        assert min_size.y == 20  # 8 + 12

    def test_get_min_size_explicit(self):
        """Explicit minimum size should be used if provided."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(
            texture_path="button.png",
            metrics=metrics,
            min_size=Vector2(50, 40),
        )

        min_size = sprite.get_min_size()

        assert min_size.x == 50
        assert min_size.y == 40

    def test_get_patch_rects_uniform(self):
        """Patch rectangles should be calculated correctly for uniform metrics."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        # Source texture is 100x100
        src_rects = sprite.get_patch_rects(100, 100)

        # Check corners (fixed size)
        assert src_rects[0] == Rect(0, 0, 10, 10)  # Top-Left
        assert src_rects[2] == Rect(90, 0, 10, 10)  # Top-Right
        assert src_rects[6] == Rect(0, 90, 10, 10)  # Bottom-Left
        assert src_rects[8] == Rect(90, 90, 10, 10)  # Bottom-Right

        # Check edges
        assert src_rects[1] == Rect(10, 0, 80, 10)  # Top edge
        assert src_rects[3] == Rect(0, 10, 10, 80)  # Left edge
        assert src_rects[5] == Rect(90, 10, 10, 80)  # Right edge
        assert src_rects[7] == Rect(10, 90, 80, 10)  # Bottom edge

        # Check center
        assert src_rects[4] == Rect(10, 10, 80, 80)  # Center

    def test_get_patch_rects_asymmetric(self):
        """Patch rectangles should handle asymmetric metrics."""
        metrics = NinePatchMetrics(left=5, right=15, top=10, bottom=20)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        # Source texture is 100x100
        src_rects = sprite.get_patch_rects(100, 100)

        # Check corners with different sizes
        assert src_rects[0] == Rect(0, 0, 5, 10)  # Top-Left
        assert src_rects[2] == Rect(85, 0, 15, 10)  # Top-Right
        assert src_rects[6] == Rect(0, 80, 5, 20)  # Bottom-Left
        assert src_rects[8] == Rect(85, 80, 15, 20)  # Bottom-Right

        # Check center dimensions
        assert src_rects[4] == Rect(5, 10, 80, 70)  # 100-5-15=80, 100-10-20=70

    def test_get_dest_rects_no_stretch(self):
        """Destination rects should match source when rendering at minimum size."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        # Render at exactly min size (20x20)
        dest_rects = sprite.get_dest_rects(x=0, y=0, width=20, height=20)

        # Corners should be 10x10
        assert dest_rects[0] == Rect(0, 0, 10, 10)  # Top-Left
        assert dest_rects[2] == Rect(10, 0, 10, 10)  # Top-Right
        assert dest_rects[6] == Rect(0, 10, 10, 10)  # Bottom-Left
        assert dest_rects[8] == Rect(10, 10, 10, 10)  # Bottom-Right

        # Edges and center should be 0 size (no stretching)
        assert dest_rects[1] == Rect(10, 0, 0, 10)  # Top edge
        assert dest_rects[4] == Rect(10, 10, 0, 0)  # Center

    def test_get_dest_rects_with_stretch(self):
        """Destination rects should stretch properly when larger than min size."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        # Render at 100x80 (larger than min 20x20)
        dest_rects = sprite.get_dest_rects(x=0, y=0, width=100, height=80)

        # Corners stay 10x10
        assert dest_rects[0] == Rect(0, 0, 10, 10)  # Top-Left
        assert dest_rects[2] == Rect(90, 0, 10, 10)  # Top-Right
        assert dest_rects[6] == Rect(0, 70, 10, 10)  # Bottom-Left
        assert dest_rects[8] == Rect(90, 70, 10, 10)  # Bottom-Right

        # Edges stretch
        assert dest_rects[1] == Rect(10, 0, 80, 10)  # Top edge (stretch width)
        assert dest_rects[3] == Rect(0, 10, 10, 60)  # Left edge (stretch height)
        assert dest_rects[5] == Rect(90, 10, 10, 60)  # Right edge (stretch height)
        assert dest_rects[7] == Rect(10, 70, 80, 10)  # Bottom edge (stretch width)

        # Center stretches in both directions
        assert dest_rects[4] == Rect(10, 10, 80, 60)  # Center

    def test_get_dest_rects_with_offset(self):
        """Destination rects should account for position offset."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        # Render at position (50, 30) with size 60x50
        dest_rects = sprite.get_dest_rects(x=50, y=30, width=60, height=50)

        # Check that positions are offset
        assert dest_rects[0] == Rect(50, 30, 10, 10)  # Top-Left
        assert dest_rects[2] == Rect(100, 30, 10, 10)  # Top-Right (50+60-10)
        assert dest_rects[6] == Rect(50, 70, 10, 10)  # Bottom-Left (30+50-10)
        assert dest_rects[8] == Rect(100, 70, 10, 10)  # Bottom-Right

        # Check stretched dimensions
        assert dest_rects[4] == Rect(60, 40, 40, 30)  # Center (60-20, 50-20)

    def test_get_dest_rects_enforces_min_size(self):
        """Destination rects should not render smaller than minimum size."""
        metrics = NinePatchMetrics.uniform(10)
        sprite = NinePatchSprite(texture_path="button.png", metrics=metrics)

        # Try to render at 10x10 (smaller than min 20x20)
        dest_rects = sprite.get_dest_rects(x=0, y=0, width=10, height=10)

        # Should be clamped to min size (20x20)
        # Total width should be 20 (left 10 + center 0 + right 10)
        assert dest_rects[0].width == 10
        assert dest_rects[2].x == 10  # Right corner at x=10
        assert dest_rects[8].y == 10  # Bottom corner at y=10


class TestNinePatchUsagePatterns:
    """Test common usage patterns for nine-patch sprites."""

    def test_button_with_uniform_corners(self):
        """Common pattern: button with uniform corner radius."""
        # Button texture with 8px rounded corners
        metrics = NinePatchMetrics.uniform(8)
        button = NinePatchSprite(
            texture_path="assets/button.png",
            metrics=metrics,
        )

        # Render at various sizes
        dest_small = button.get_dest_rects(x=10, y=10, width=64, height=32)
        dest_large = button.get_dest_rects(x=10, y=10, width=200, height=60)

        # Corners always 8x8
        assert dest_small[0] == Rect(10, 10, 8, 8)
        assert dest_large[0] == Rect(10, 10, 8, 8)

        # Centers scale appropriately
        assert dest_small[4].width == 48  # 64 - 16
        assert dest_large[4].width == 184  # 200 - 16

    def test_panel_with_thick_border(self):
        """Common pattern: panel with decorative border."""
        # Panel with 20px ornate border on all sides
        metrics = NinePatchMetrics.uniform(20)
        panel = NinePatchSprite(
            texture_path="assets/panel.png",
            metrics=metrics,
        )

        # Large panel
        dest_rects = panel.get_dest_rects(x=0, y=0, width=400, height=300)

        # Border stays 20px
        assert dest_rects[1].height == 20  # Top edge
        assert dest_rects[3].width == 20  # Left edge

        # Large content area
        assert dest_rects[4].width == 360  # 400 - 40
        assert dest_rects[4].height == 260  # 300 - 40

    def test_dialog_with_title_bar(self):
        """Common pattern: dialog with asymmetric top bar."""
        # Dialog with 30px title bar, 10px other edges
        metrics = NinePatchMetrics(left=10, right=10, top=30, bottom=10)
        dialog = NinePatchSprite(
            texture_path="assets/dialog.png",
            metrics=metrics,
        )

        dest_rects = dialog.get_dest_rects(x=100, y=100, width=300, height=200)

        # Title bar is 30px
        assert dest_rects[1].height == 30  # Top edge

        # Other edges are 10px
        assert dest_rects[3].width == 10  # Left edge
        assert dest_rects[7].height == 10  # Bottom edge

        # Content area accounts for asymmetry
        assert dest_rects[4].height == 160  # 200 - 30 - 10
