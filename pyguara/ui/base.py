"""Base UI Component classes."""

from abc import ABC, abstractmethod
from typing import List, Optional, Callable, TYPE_CHECKING

from pyguara.common.types import Vector2, Rect
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.types import UIAnchor, UIElementState, UIEventType
from pyguara.ui.theme import get_theme

if TYPE_CHECKING:
    from pyguara.ui.constraints import LayoutConstraints, Padding


class UIElement(ABC):
    """Base class for all UI components."""

    def __init__(
        self,
        position: Vector2,
        size: Vector2,
        anchor: UIAnchor = UIAnchor.TOP_LEFT,
        visible: bool = True,
    ) -> None:
        """Initialize the UI element."""
        # Use Engine Types, not Pygame Types
        self.rect = Rect(int(position.x), int(position.y), int(size.x), int(size.y))
        self.anchor = anchor
        self.visible = visible
        self.enabled = True

        self.state = UIElementState.NORMAL
        self.parent: Optional["UIElement"] = None
        self.children: List["UIElement"] = []

        # Layout
        self.constraints: Optional["LayoutConstraints"] = None
        self.padding: Optional["Padding"] = None

        # Theme Integration
        self.theme = get_theme()

        # Callbacks
        self.on_click: Optional[Callable[["UIElement"], None]] = None

    @abstractmethod
    def render(self, renderer: UIRenderer) -> None:
        """Draw the element using the abstract renderer."""
        pass

    def update(self, dt: float) -> None:
        """Process animations or logic."""
        for child in self.children:
            if child.visible:
                child.update(dt)

    def handle_event(
        self, event_type: UIEventType, position: Vector2, button: int = 0
    ) -> bool:
        """Process generic input event.

        Args:
            event_type: The type of UI event (mouse, focus, etc.).
            position: The position of the event in screen coordinates.
            button: The mouse button number (1=left, 2=middle, 3=right).

        Returns:
            True if the event was consumed by this element or its children.

        Example:
            >>> element.handle_event(UIEventType.MOUSE_DOWN, Vector2(100, 50), 1)
            True
        """
        if not self.visible or not self.enabled:
            return False

        # 1. Bubbling: Children get first dibs (reverse order for z-index)
        for child in reversed(self.children):
            if child.handle_event(event_type, position, button):
                return True

        # 2. Self Processing
        return self._process_input(event_type, position, button)

    def _process_input(
        self, event_type: UIEventType, position: Vector2, button: int
    ) -> bool:
        """Perform internal input logic (e.g. click detection)."""
        # Simple containment check using our Rect type
        contains = (
            self.rect.x <= position.x <= self.rect.x + self.rect.width
            and self.rect.y <= position.y <= self.rect.y + self.rect.height
        )

        if event_type == UIEventType.MOUSE_MOVE:
            if contains:
                if self.state != UIElementState.PRESSED:
                    self.state = UIElementState.HOVERED
                return True  # Consume hover
            else:
                if self.state == UIElementState.HOVERED:
                    self.state = UIElementState.NORMAL

        elif event_type == UIEventType.MOUSE_DOWN:
            if contains and button == 1:
                self.state = UIElementState.PRESSED
                return True  # Consume click

        elif event_type == UIEventType.MOUSE_UP:
            if self.state == UIElementState.PRESSED:
                if contains:
                    self.state = UIElementState.HOVERED
                    if self.on_click:
                        self.on_click(self)
                else:
                    self.state = UIElementState.NORMAL
                return True

        return False

    def add_child(self, child: "UIElement") -> None:
        """Add a child element to this container."""
        child.parent = self
        self.children.append(child)

    def apply_layout(self) -> None:
        """Apply layout constraints to this element and its children.

        Applies constraints relative to parent if present.
        Then recursively applies layout to children.
        """
        # Apply own constraints if present and has parent
        if self.constraints and self.parent:
            self.rect = self.constraints.apply(self.rect, self.parent.rect)

        # Apply layout to children
        for child in self.children:
            if child.visible:
                child.apply_layout()

    def get_content_rect(self) -> Rect:
        """Get the rectangle for content area (rect minus padding).

        Returns:
            Content rectangle accounting for padding
        """
        if self.padding:
            return Rect(
                self.rect.x + self.padding.left,
                self.rect.y + self.padding.top,
                self.rect.width - self.padding.horizontal_total,
                self.rect.height - self.padding.vertical_total,
            )
        return self.rect
