"""Base UI Component classes."""

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

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

        # Whether keyboard traversal can land on this element. Off by
        # default: a container, a label or a decorative panel is not a stop
        # on the Tab ring, and opting in is a smaller thing to get right
        # than opting every layout box out.
        self.focusable = False

        # Callbacks
        self.on_click: Callable[[UIElement], None] | None = None

        # Whether the focus ring is currently on this element. Kept apart
        # from `state` because focus outlives a hover: a focused button the
        # mouse then passes over must go back to looking focused when the
        # cursor leaves, not to looking idle.
        self._focused = False

        # Whether that focus should actually be *painted*. Set on keyboard
        # traversal (Tab, arrows) and cleared on a mouse click or a
        # programmatic `set_focus()` -- the standard focus-visible split.
        # `state` still becomes FOCUSED either way, since the element *is*
        # focused and still gets the keyboard; this only gates the ring a
        # component draws for it. Without the split, every button a mouse
        # user last clicked -- and the one a screen pre-focuses on build,
        # before any key was ever pressed -- sat under a bright outline
        # nobody asked to see.
        self.focus_visible = False

        # Set by `UIManager.add_element` on a root, so an element can tell
        # the manager its layout is stale -- a label whose text changed is
        # a different width, and nothing else can see that.
        self._manager: Any | None = None

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

        # Motion reaches *every* child, and a click only the first that
        # takes it. A click is exclusive -- one press, one button -- but
        # hover is a fact about where the cursor is, which every element
        # needs to hear whether or not it is the one under it. Stopping
        # motion at the first consumer left the element the cursor just
        # came *off* believing it was still hovered, so two neighbouring
        # buttons both sat lit until the cursor landed on empty space.
        if event_type == UIEventType.MOUSE_MOVE:
            consumed = False
            for child in reversed(self.children):
                consumed |= child.handle_event(event_type, position, button)
            return self._process_input(event_type, position, button) or consumed

        # 1. Bubbling: Children get first dibs (reverse order for z-index)
        for child in reversed(self.children):
            if child.handle_event(event_type, position, button):
                return True

        # 2. Self Processing
        return self._process_input(event_type, position, button)

    def set_focused(self, focused: bool, *, visible: bool = False) -> None:
        """Mark this element as holding (or losing) the focus ring.

        `UIElementState.FOCUSED` was read by `Button`, `Checkbox` and the
        design-system components long before anything assigned it, so Tab
        moved the ring invisibly. This is what assigns it.

        Args:
            focused: Whether the ring is now on this element.
            visible: Whether a component should actually *paint* the ring
                for it. Ignored when `focused` is False -- losing focus
                always clears visibility too.
        """
        self._focused = focused
        self.focus_visible = visible and focused
        if self.state not in (UIElementState.PRESSED, UIElementState.HOVERED):
            self.state = self._resting_state()

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable the element, and show it.

        Args:
            enabled: Whether the element accepts input.
        """
        self.enabled = enabled
        self.state = self._resting_state()

    def _resting_state(self) -> UIElementState:
        """Return the state for an element neither hovered nor held."""
        if not self.enabled:
            return UIElementState.DISABLED
        if self._focused:
            return UIElementState.FOCUSED
        return UIElementState.NORMAL

    def invalidate_layout(self) -> None:
        """Tell the manager this element's layout is stale.

        Walks up to the root, since the manager only knows about roots. A
        no-op for an element that is not in a manager.
        """
        element: UIElement = self
        while element.parent is not None:
            element = element.parent
        if element._manager is not None:
            element._manager.invalidate_layout()

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
                    self.state = self._resting_state()

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
                    self.state = self._resting_state()
                return True

        return False

    def add_child(self, child: "UIElement") -> None:
        """Add a child element to this container."""
        child.parent = self
        self.children.append(child)

    def hit_test(self, position: Vector2) -> "UIElement":
        """Return the deepest visible, enabled descendant under `position`.

        Front-to-back, mirroring the order `handle_event()` bubbles in.
        Used to find *what was actually clicked* -- `handle_event()` only
        reports whether something under this element consumed the event,
        not which element that was, which is enough to route input but not
        enough to focus the right thing. A click inside a `BoxContainer` of
        buttons used to focus the container itself.

        Args:
            position: The point to test, in the same space as `self.rect`.

        Returns:
            The deepest matching descendant, or `self` if none of this
            element's children contain the point.
        """
        for child in reversed(self.children):
            if not child.visible or not child.enabled:
                continue
            contains = (
                child.rect.x <= position.x <= child.rect.x + child.rect.width
                and child.rect.y <= position.y <= child.rect.y + child.rect.height
            )
            if contains:
                return child.hit_test(position)
        return self

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
