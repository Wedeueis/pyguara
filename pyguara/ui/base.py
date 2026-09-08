"""Base UI Component classes."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING

from pyguara.common.types import Rect, Vector2
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.theme import get_theme
from pyguara.ui.types import UIElementState, UIEventType

if TYPE_CHECKING:
    from pyguara.ui.constraints import LayoutConstraints, Padding
    from pyguara.ui.theme import UITheme


class UIElement(ABC):
    """Base class for all UI components."""

    def __init__(
        self,
        position: Vector2,
        size: Vector2,
        visible: bool = True,
    ) -> None:
        """Initialize the UI element."""
        # Use Engine Types, not Pygame Types
        self.rect = Rect(int(position.x), int(position.y), int(size.x), int(size.y))
        self.visible = visible
        self.enabled = True

        self.state = UIElementState.NORMAL
        self.parent: UIElement | None = None
        self.children: list[UIElement] = []

        # Layout
        self.constraints: LayoutConstraints | None = None
        self.padding: Padding | None = None

        # Callbacks
        self.on_click: Callable[[UIElement], None] | None = None

    @property
    def theme(self) -> "UITheme":
        """The active global theme.

        Looked up live on every access rather than captured at construction,
        so `set_theme()` re-skins elements that already exist.
        """
        return get_theme()

    @abstractmethod
    def render(self, renderer: UIRenderer) -> None:
        """Draw the element using the abstract renderer."""
        pass

    def measure(self, renderer: UIRenderer) -> None:
        """Recompute this element's own size, if it depends on renderer state.

        No-op by default -- most elements have a fixed size. Override to set
        `self.rect.width`/`height` from renderer-measured content (e.g. text),
        called both by `render()` (so a standalone element still sizes itself
        before drawing) and by a parent container's `layout()` (so sibling
        stacking math sees the real size, not a placeholder).
        """
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

    def layout(self, available_rect: Rect, renderer: UIRenderer) -> None:
        """Resolve this element's rect, then its children's, for one frame.

        `UIManager` runs this over every root before rendering, and again
        after a window resize or an explicit `UIManager.invalidate_layout()`.
        `available_rect` is the space this element may occupy: the screen for
        a root element, the parent's content rect for a child.

        The default implementation measures the element, applies its
        `constraints` against `available_rect` if it has any, then lays each
        visible child out inside this element's content rect (so `padding`
        finally takes effect). Containers that position their own children --
        see `BoxContainer` -- override this.

        Args:
            available_rect: The rectangle this element may lay itself out in.
            renderer: Passed to `measure()` so text-sized elements report a
                real size before constraint math reads it.
        """
        self.measure(renderer)

        if self.constraints:
            self.rect = self.constraints.apply(self.rect, available_rect)

        content = self.get_content_rect()
        for child in self.children:
            if child.visible:
                child.layout(content, renderer)

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
