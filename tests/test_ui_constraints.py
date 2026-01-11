"""Tests for UI layout constraints system."""

from pyguara.common.types import Vector2, Rect
from pyguara.ui.constraints import (
    LayoutConstraints,
    Margin,
    Padding,
    create_anchored_constraints,
    create_centered_constraints,
    create_fill_constraints,
)
from pyguara.ui.types import UIAnchor


class TestMargin:
    """Test Margin spacing."""

    def test_margin_creation(self):
        """Margin should be created with individual values."""
        margin = Margin(top=10, bottom=20, left=15, right=25)

        assert margin.top == 10
        assert margin.bottom == 20
        assert margin.left == 15
        assert margin.right == 25

    def test_margin_defaults(self):
        """Margin should default to 0."""
        margin = Margin()

        assert margin.top == 0
        assert margin.bottom == 0
        assert margin.left == 0
        assert margin.right == 0

    def test_margin_all(self):
        """Margin.all() should create uniform margin."""
        margin = Margin.all(10)

        assert margin.top == 10
        assert margin.bottom == 10
        assert margin.left == 10
        assert margin.right == 10

    def test_margin_symmetric(self):
        """Margin.symmetric() should create symmetric margins."""
        margin = Margin.symmetric(vertical=20, horizontal=10)

        assert margin.top == 20
        assert margin.bottom == 20
        assert margin.left == 10
        assert margin.right == 10

    def test_margin_horizontal_total(self):
        """horizontal_total should return left + right."""
        margin = Margin(left=10, right=20)

        assert margin.horizontal_total == 30

    def test_margin_vertical_total(self):
        """vertical_total should return top + bottom."""
        margin = Margin(top=10, bottom=20)

        assert margin.vertical_total == 30


class TestPadding:
    """Test Padding spacing."""

    def test_padding_creation(self):
        """Padding should be created with individual values."""
        padding = Padding(top=5, bottom=10, left=8, right=12)

        assert padding.top == 5
        assert padding.bottom == 10
        assert padding.left == 8
        assert padding.right == 12

    def test_padding_defaults(self):
        """Padding should default to 0."""
        padding = Padding()

        assert padding.top == 0
        assert padding.bottom == 0
        assert padding.left == 0
        assert padding.right == 0

    def test_padding_all(self):
        """Padding.all() should create uniform padding."""
        padding = Padding.all(15)

        assert padding.top == 15
        assert padding.bottom == 15
        assert padding.left == 15
        assert padding.right == 15

    def test_padding_symmetric(self):
        """Padding.symmetric() should create symmetric padding."""
        padding = Padding.symmetric(vertical=10, horizontal=5)

        assert padding.top == 10
        assert padding.bottom == 10
        assert padding.left == 5
        assert padding.right == 5

    def test_padding_horizontal_total(self):
        """horizontal_total should return left + right."""
        padding = Padding(left=8, right=12)

        assert padding.horizontal_total == 20

    def test_padding_vertical_total(self):
        """vertical_total should return top + bottom."""
        padding = Padding(top=8, bottom=12)

        assert padding.vertical_total == 20


class TestLayoutConstraints:
    """Test LayoutConstraints positioning."""

    def test_constraints_creation(self):
        """LayoutConstraints should be created with defaults."""
        constraints = LayoutConstraints()

        assert constraints.anchor == UIAnchor.TOP_LEFT
        assert isinstance(constraints.margin, Margin)
        assert constraints.offset == Vector2.zero()

    def test_top_left_anchor(self):
        """TOP_LEFT anchor should position at top-left."""
        constraints = LayoutConstraints(anchor=UIAnchor.TOP_LEFT)

        element_rect = Rect(0, 0, 100, 50)
        parent_rect = Rect(0, 0, 400, 300)

        result = constraints.apply(element_rect, parent_rect)

        assert result.x == 0
        assert result.y == 0
        assert result.width == 100
        assert result.height == 50

    def test_center_anchor(self):
        """CENTER anchor should position at center."""
        constraints = LayoutConstraints(anchor=UIAnchor.CENTER)

        element_rect = Rect(0, 0, 100, 50)
        parent_rect = Rect(0, 0, 400, 300)

        result = constraints.apply(element_rect, parent_rect)

        # Center horizontally: (400 - 100) / 2 = 150
        # Center vertically: (300 - 50) / 2 = 125
        assert result.x == 150
        assert result.y == 125

    def test_bottom_right_anchor(self):
        """BOTTOM_RIGHT anchor should position at bottom-right."""
        constraints = LayoutConstraints(anchor=UIAnchor.BOTTOM_RIGHT)

        element_rect = Rect(0, 0, 100, 50)
        parent_rect = Rect(0, 0, 400, 300)

        result = constraints.apply(element_rect, parent_rect)

        assert result.x == 300  # 400 - 100
        assert result.y == 250  # 300 - 50

    def test_top_center_anchor(self):
        """TOP_CENTER anchor should position at top center."""
        constraints = LayoutConstraints(anchor=UIAnchor.TOP_CENTER)

        element_rect = Rect(0, 0, 100, 50)
        parent_rect = Rect(0, 0, 400, 300)

        result = constraints.apply(element_rect, parent_rect)

        assert result.x == 150  # (400 - 100) / 2
        assert result.y == 0

    def test_margin_application(self):
        """Margins should reduce available space."""
        constraints = LayoutConstraints(
            anchor=UIAnchor.TOP_LEFT,
            margin=Margin(top=10, left=20, bottom=30, right=40),
        )

        element_rect = Rect(0, 0, 100, 50)
        parent_rect = Rect(0, 0, 400, 300)

        result = constraints.apply(element_rect, parent_rect)

        # Should start at margin position
        assert result.x == 20
        assert result.y == 10

    def test_margin_with_center(self):
        """Margins should affect centering."""
        constraints = LayoutConstraints(anchor=UIAnchor.CENTER, margin=Margin.all(50))

        element_rect = Rect(0, 0, 100, 50)
        parent_rect = Rect(0, 0, 400, 300)

        result = constraints.apply(element_rect, parent_rect)

        # Available space: 400 - 100 (margins) = 300 width
        # Center in available: 50 + (300 - 100) / 2 = 150
        assert result.x == 150
        # Available height: 300 - 100 (margins) = 200 height
        # Center in available: 50 + (200 - 50) / 2 = 125
        assert result.y == 125

    def test_offset_application(self):
        """Offset should shift position after anchor calculation."""
        constraints = LayoutConstraints(
            anchor=UIAnchor.TOP_LEFT, offset=Vector2(10, 20)
        )

        element_rect = Rect(0, 0, 100, 50)
        parent_rect = Rect(0, 0, 400, 300)

        result = constraints.apply(element_rect, parent_rect)

        assert result.x == 10
        assert result.y == 20

    def test_width_percent(self):
        """width_percent should set width as percentage of parent."""
        constraints = LayoutConstraints(anchor=UIAnchor.TOP_LEFT, width_percent=0.5)

        element_rect = Rect(0, 0, 100, 50)
        parent_rect = Rect(0, 0, 400, 300)

        result = constraints.apply(element_rect, parent_rect)

        assert result.width == 200  # 50% of 400

    def test_height_percent(self):
        """height_percent should set height as percentage of parent."""
        constraints = LayoutConstraints(anchor=UIAnchor.TOP_LEFT, height_percent=0.75)

        element_rect = Rect(0, 0, 100, 50)
        parent_rect = Rect(0, 0, 400, 300)

        result = constraints.apply(element_rect, parent_rect)

        assert result.height == 225  # 75% of 300

    def test_min_size_constraint(self):
        """min_size should prevent element from being too small."""
        constraints = LayoutConstraints(
            anchor=UIAnchor.TOP_LEFT,
            width_percent=0.1,  # Would be 40
            min_size=Vector2(100, 100),
        )

        element_rect = Rect(0, 0, 50, 50)
        parent_rect = Rect(0, 0, 400, 300)

        result = constraints.apply(element_rect, parent_rect)

        assert result.width == 100  # Clamped to min
        assert result.height == 100  # Clamped to min

    def test_max_size_constraint(self):
        """max_size should prevent element from being too large."""
        constraints = LayoutConstraints(
            anchor=UIAnchor.TOP_LEFT,
            width_percent=0.8,  # Would be 320
            height_percent=1.0,  # Would be 300
            max_size=Vector2(200, 150),
        )

        element_rect = Rect(0, 0, 100, 100)
        parent_rect = Rect(0, 0, 400, 300)

        result = constraints.apply(element_rect, parent_rect)

        assert result.width == 200  # Clamped to max from 320
        assert result.height == 150  # Clamped to max from 300

    def test_parent_offset(self):
        """Constraints should work with parent at non-zero position."""
        constraints = LayoutConstraints(anchor=UIAnchor.TOP_LEFT)

        element_rect = Rect(0, 0, 100, 50)
        parent_rect = Rect(50, 100, 400, 300)  # Parent at (50, 100)

        result = constraints.apply(element_rect, parent_rect)

        # Should be at parent's position
        assert result.x == 50
        assert result.y == 100


class TestConstraintFactories:
    """Test constraint factory functions."""

    def test_create_anchored_constraints(self):
        """create_anchored_constraints should create simple anchored layout."""
        constraints = create_anchored_constraints(
            UIAnchor.BOTTOM_RIGHT, margin=10, offset_x=5, offset_y=15
        )

        assert constraints.anchor == UIAnchor.BOTTOM_RIGHT
        assert constraints.margin.top == 10
        assert constraints.margin.bottom == 10
        assert constraints.offset == Vector2(5, 15)

    def test_create_centered_constraints(self):
        """create_centered_constraints should create centered layout."""
        constraints = create_centered_constraints(
            width_percent=0.8, height_percent=0.6, margin=20
        )

        assert constraints.anchor == UIAnchor.CENTER
        assert constraints.width_percent == 0.8
        assert constraints.height_percent == 0.6
        assert constraints.margin.top == 20

    def test_create_fill_constraints(self):
        """create_fill_constraints should create fill-parent layout."""
        constraints = create_fill_constraints(margin=15)

        assert constraints.anchor == UIAnchor.TOP_LEFT
        assert constraints.width_percent == 1.0
        assert constraints.height_percent == 1.0
        assert constraints.margin.top == 15


class TestConstraintIntegration:
    """Test constraint system integration scenarios."""

    def test_responsive_layout(self):
        """Constraints should adapt to different parent sizes."""
        constraints = create_centered_constraints(width_percent=0.5, height_percent=0.5)

        element_rect = Rect(0, 0, 100, 100)

        # Small parent
        small_parent = Rect(0, 0, 400, 300)
        result1 = constraints.apply(element_rect, small_parent)
        assert result1.width == 200
        assert result1.height == 150

        # Large parent
        large_parent = Rect(0, 0, 800, 600)
        result2 = constraints.apply(element_rect, large_parent)
        assert result2.width == 400
        assert result2.height == 300

    def test_dialog_centered(self):
        """Dialog pattern: centered with fixed size and margin."""
        constraints = LayoutConstraints(
            anchor=UIAnchor.CENTER,
            margin=Margin.all(50),
            min_size=Vector2(300, 200),
            max_size=Vector2(600, 400),
        )

        element_rect = Rect(0, 0, 400, 250)
        parent_rect = Rect(0, 0, 1920, 1080)

        result = constraints.apply(element_rect, parent_rect)

        # Size should stay as is (within min/max range)
        assert result.width == 400
        assert result.height == 250
        # Should be centered in available space (1920-100, 1080-100)
        # Center X: 50 + (1820 - 400) / 2 = 50 + 710 = 760
        # Center Y: 50 + (980 - 250) / 2 = 50 + 365 = 415
        assert result.x == 760
        assert result.y == 415

    def test_sidebar_pattern(self):
        """Sidebar pattern: fixed width, fill height."""
        constraints = LayoutConstraints(
            anchor=UIAnchor.TOP_LEFT,
            width_percent=0.2,  # 20% width
            height_percent=1.0,  # Full height
            max_size=Vector2(300, 10000),  # Max 300px wide
        )

        element_rect = Rect(0, 0, 100, 100)
        parent_rect = Rect(0, 0, 1920, 1080)

        result = constraints.apply(element_rect, parent_rect)

        assert result.width == 300  # Clamped to max
        assert result.height == 1080  # Full height
        assert result.x == 0
        assert result.y == 0

    def test_footer_pattern(self):
        """Footer pattern: full width, anchored to bottom."""
        constraints = LayoutConstraints(
            anchor=UIAnchor.BOTTOM_LEFT,
            width_percent=1.0,
            margin=Margin.symmetric(horizontal=20),
        )

        element_rect = Rect(0, 0, 100, 50)
        parent_rect = Rect(0, 0, 800, 600)

        result = constraints.apply(element_rect, parent_rect)

        # Width: 800 - 40 (margins) = 760
        assert result.width == 760
        assert result.height == 50
        assert result.x == 20  # Left margin
        assert result.y == 550  # Bottom: 600 - 50


class TestPaddingIntegration:
    """Test padding usage patterns."""

    def test_padding_content_area(self):
        """Padding should create inner content area."""
        from pyguara.ui.components.panel import Panel

        panel = Panel(Vector2(0, 0), Vector2(200, 100))
        panel.padding = Padding.all(10)

        content_rect = panel.get_content_rect()

        assert content_rect.x == 10
        assert content_rect.y == 10
        assert content_rect.width == 180  # 200 - 20
        assert content_rect.height == 80  # 100 - 20

    def test_asymmetric_padding(self):
        """Asymmetric padding should work correctly."""
        from pyguara.ui.components.panel import Panel

        panel = Panel(Vector2(50, 50), Vector2(300, 200))
        panel.padding = Padding(top=5, bottom=15, left=10, right=20)

        content_rect = panel.get_content_rect()

        assert content_rect.x == 60  # 50 + 10
        assert content_rect.y == 55  # 50 + 5
        assert content_rect.width == 270  # 300 - 30
        assert content_rect.height == 180  # 200 - 20


class TestLayoutUsagePatterns:
    """Test common layout usage patterns."""

    def test_card_grid_item(self):
        """Card in grid: centered with margin."""
        constraints = create_anchored_constraints(UIAnchor.TOP_LEFT, margin=10)

        element_rect = Rect(0, 0, 150, 200)
        parent_rect = Rect(0, 0, 170, 220)  # Grid cell

        result = constraints.apply(element_rect, parent_rect)

        assert result.x == 10
        assert result.y == 10

    def test_modal_overlay(self):
        """Modal overlay: full screen with semi-transparent background."""
        constraints = create_fill_constraints(margin=0)

        element_rect = Rect(0, 0, 100, 100)
        parent_rect = Rect(0, 0, 1920, 1080)

        result = constraints.apply(element_rect, parent_rect)

        assert result.width == 1920
        assert result.height == 1080
        assert result.x == 0
        assert result.y == 0

    def test_notification_toast(self):
        """Toast notification: top-right corner with offset."""
        constraints = LayoutConstraints(
            anchor=UIAnchor.TOP_RIGHT,
            margin=Margin(top=20, right=20),
            offset=Vector2(-10, 0),  # Extra offset from edge
        )

        element_rect = Rect(0, 0, 300, 80)
        parent_rect = Rect(0, 0, 1920, 1080)

        result = constraints.apply(element_rect, parent_rect)

        # Should be at top-right with margins and offset
        assert result.x == 1590  # 1920 - 20 (margin) - 300 (width) - 10 (offset)
        assert result.y == 20

    def test_responsive_button(self):
        """Button that scales with parent but has min/max size."""
        constraints = LayoutConstraints(
            anchor=UIAnchor.CENTER,
            width_percent=0.8,
            margin=Margin.symmetric(vertical=10),
            min_size=Vector2(120, 40),
            max_size=Vector2(300, 60),
        )

        # Small parent (150 * 0.8 = 120, hits min)
        small_result = constraints.apply(Rect(0, 0, 100, 50), Rect(0, 0, 150, 100))
        assert small_result.width == 120  # Clamped to min

        # Large parent (500 * 0.8 = 400, clamped to 300)
        large_result = constraints.apply(Rect(0, 0, 100, 50), Rect(0, 0, 500, 100))
        assert large_result.width == 300  # Clamped to max

        # Medium parent (250 * 0.8 = 200, within range)
        medium_result = constraints.apply(Rect(0, 0, 100, 50), Rect(0, 0, 250, 100))
        assert medium_result.width == 200  # 80% of 250
