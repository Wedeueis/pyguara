"""Layout constraint system for UI elements.

This module provides constraint-based positioning for UI elements, allowing for:
- Anchor-based positioning (align to parent edges/center)
- Margin and padding support
- Relative positioning and sizing
- Percentage-based dimensions

Example:
    >>> from pyguara.ui.constraints import LayoutConstraints, Margin
    >>>
    >>> # Center element with margins
    >>> constraints = LayoutConstraints(
    ...     anchor=UIAnchor.CENTER,
    ...     margin=Margin(top=10, bottom=10, left=20, right=20)
    ... )
    >>> element.constraints = constraints
    >>> constraints.apply(element, parent_rect)
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from pyguara.common.types import Vector2, Rect
from pyguara.ui.types import UIAnchor

if TYPE_CHECKING:
    from pyguara.ui.base import UIElement


@dataclass
class Margin:
    """Margin spacing around an element.

    Margins create space OUTSIDE the element's boundaries.

    Attributes:
        top: Top margin in pixels
        bottom: Bottom margin in pixels
        left: Left margin in pixels
        right: Right margin in pixels
    """

    top: int = 0
    bottom: int = 0
    left: int = 0
    right: int = 0

    @classmethod
    def all(cls, value: int) -> "Margin":
        """Create uniform margin on all sides."""
        return cls(top=value, bottom=value, left=value, right=value)

    @classmethod
    def symmetric(cls, vertical: int = 0, horizontal: int = 0) -> "Margin":
        """Create symmetric margins."""
        return cls(top=vertical, bottom=vertical, left=horizontal, right=horizontal)

    @property
    def horizontal_total(self) -> int:
        """Total horizontal margin (left + right)."""
        return self.left + self.right

    @property
    def vertical_total(self) -> int:
        """Total vertical margin (top + bottom)."""
        return self.top + self.bottom


@dataclass
class Padding:
    """Padding spacing inside an element.

    Padding creates space INSIDE the element's boundaries,
    between the border and content.

    Attributes:
        top: Top padding in pixels
        bottom: Bottom padding in pixels
        left: Left padding in pixels
        right: Right padding in pixels
    """

    top: int = 0
    bottom: int = 0
    left: int = 0
    right: int = 0

    @classmethod
    def all(cls, value: int) -> "Padding":
        """Create uniform padding on all sides."""
        return cls(top=value, bottom=value, left=value, right=value)

    @classmethod
    def symmetric(cls, vertical: int = 0, horizontal: int = 0) -> "Padding":
        """Create symmetric padding."""
        return cls(top=vertical, bottom=vertical, left=horizontal, right=horizontal)

    @property
    def horizontal_total(self) -> int:
        """Total horizontal padding (left + right)."""
        return self.left + self.right

    @property
    def vertical_total(self) -> int:
        """Total vertical padding (top + bottom)."""
        return self.top + self.bottom


@dataclass
class LayoutConstraints:
    """Layout constraints for UI element positioning and sizing.

    Controls how an element is positioned relative to its parent.

    Attributes:
        anchor: Anchor point for positioning
        margin: Margin spacing around element
        offset: Additional offset from anchor position
        min_size: Minimum size (width, height) in pixels
        max_size: Maximum size (width, height) in pixels
        width_percent: Width as percentage of parent (0.0-1.0)
        height_percent: Height as percentage of parent (0.0-1.0)
        keep_aspect_ratio: Maintain aspect ratio when resizing
    """

    anchor: UIAnchor = UIAnchor.TOP_LEFT
    margin: Margin = field(default_factory=Margin)
    offset: Vector2 = field(default_factory=Vector2.zero)

    # Size constraints
    min_size: Optional[Vector2] = None
    max_size: Optional[Vector2] = None

    # Relative sizing
    width_percent: Optional[float] = None
    height_percent: Optional[float] = None
    keep_aspect_ratio: bool = False

    def apply(
        self,
        element_rect: Rect,
        parent_rect: Rect,
        element_size: Optional[Vector2] = None,
    ) -> Rect:
        """Apply constraints to position and size an element.

        Args:
            element_rect: Current element rectangle
            parent_rect: Parent container rectangle
            element_size: Optional desired size (overrides element_rect size)

        Returns:
            New rectangle with constraints applied
        """
        # Calculate available space (parent minus margins)
        available_rect = Rect(
            parent_rect.x + self.margin.left,
            parent_rect.y + self.margin.top,
            parent_rect.width - self.margin.horizontal_total,
            parent_rect.height - self.margin.vertical_total,
        )

        # Determine element size
        if element_size is None:
            element_size = Vector2(element_rect.width, element_rect.height)

        # Calculate new width
        new_width = element_size.x
        if self.width_percent is not None:
            new_width = available_rect.width * self.width_percent

        # Calculate new height
        new_height = element_size.y
        if self.height_percent is not None:
            new_height = available_rect.height * self.height_percent

        # Apply size constraints
        if self.min_size:
            new_width = max(new_width, self.min_size.x)
            new_height = max(new_height, self.min_size.y)

        if self.max_size:
            new_width = min(new_width, self.max_size.x)
            new_height = min(new_height, self.max_size.y)

        # Create new element_size with constrained dimensions
        element_size = Vector2(new_width, new_height)

        # Calculate position based on anchor
        position = self._calculate_anchor_position(
            available_rect, element_size, self.anchor
        )

        # Apply offset
        position = position + self.offset

        return Rect(
            int(position.x), int(position.y), int(element_size.x), int(element_size.y)
        )

    def _calculate_anchor_position(
        self, available_rect: Rect, element_size: Vector2, anchor: UIAnchor
    ) -> Vector2:
        """Calculate element position based on anchor point."""
        x = float(available_rect.x)
        y = float(available_rect.y)

        # Horizontal alignment
        if anchor in (
            UIAnchor.TOP_CENTER,
            UIAnchor.CENTER,
            UIAnchor.BOTTOM_CENTER,
        ):
            x = available_rect.x + (available_rect.width - element_size.x) / 2
        elif anchor in (
            UIAnchor.TOP_RIGHT,
            UIAnchor.CENTER_RIGHT,
            UIAnchor.BOTTOM_RIGHT,
        ):
            x = available_rect.x + available_rect.width - element_size.x

        # Vertical alignment
        if anchor in (
            UIAnchor.CENTER_LEFT,
            UIAnchor.CENTER,
            UIAnchor.CENTER_RIGHT,
        ):
            y = available_rect.y + (available_rect.height - element_size.y) / 2
        elif anchor in (
            UIAnchor.BOTTOM_LEFT,
            UIAnchor.BOTTOM_CENTER,
            UIAnchor.BOTTOM_RIGHT,
        ):
            y = available_rect.y + available_rect.height - element_size.y

        return Vector2(x, y)


def apply_constraints_to_element(element: "UIElement", parent_rect: Rect) -> None:
    """Apply layout constraints to a UI element if present.

    Args:
        element: UI element to constrain
        parent_rect: Parent container rectangle
    """
    if hasattr(element, "constraints") and element.constraints is not None:
        element.rect = element.constraints.apply(element.rect, parent_rect)


def create_anchored_constraints(
    anchor: UIAnchor,
    margin: int = 0,
    offset_x: int = 0,
    offset_y: int = 0,
) -> LayoutConstraints:
    """Create simple anchored constraints.

    Args:
        anchor: Anchor point
        margin: Uniform margin on all sides
        offset_x: Horizontal offset
        offset_y: Vertical offset

    Returns:
        LayoutConstraints configured for anchoring
    """
    return LayoutConstraints(
        anchor=anchor,
        margin=Margin.all(margin),
        offset=Vector2(offset_x, offset_y),
    )


def create_centered_constraints(
    width_percent: float = 1.0,
    height_percent: float = 1.0,
    margin: int = 0,
) -> LayoutConstraints:
    """Create centered layout with optional size constraints.

    Args:
        width_percent: Width as percentage of parent (0.0-1.0)
        height_percent: Height as percentage of parent (0.0-1.0)
        margin: Uniform margin on all sides

    Returns:
        LayoutConstraints configured for centering
    """
    return LayoutConstraints(
        anchor=UIAnchor.CENTER,
        margin=Margin.all(margin),
        width_percent=width_percent,
        height_percent=height_percent,
    )


def create_fill_constraints(margin: int = 0) -> LayoutConstraints:
    """Create constraints that fill parent container.

    Args:
        margin: Uniform margin on all sides

    Returns:
        LayoutConstraints configured to fill parent
    """
    return LayoutConstraints(
        anchor=UIAnchor.TOP_LEFT,
        margin=Margin.all(margin),
        width_percent=1.0,
        height_percent=1.0,
    )
