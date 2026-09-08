"""UI Manager and event integration."""

from pyguara.common.types import Rect, Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.window import WindowResizeEvent
from pyguara.graphics.protocols import UIRenderer
from pyguara.input.events import OnMouseEvent, OnRawKeyEvent
from pyguara.log import get_logger
from pyguara.ui.base import UIElement
from pyguara.ui.types import UIEventType

logger = get_logger(__name__)


class UIManager:
    """Manages the UI Scene Graph and routes engine events."""

    def __init__(self, dispatcher: EventDispatcher) -> None:
        """Initialize the UI manager and subscribe to input events."""
        self._root_elements: list[UIElement] = []
        self._dispatcher = dispatcher
        self._focused_element: UIElement | None = None

        # Space the roots lay themselves out in. Seeded by Application via
        # set_screen_size(); a resize refreshes it. Layout is skipped while
        # this is degenerate (nothing has told us the screen size yet).
        self._screen_rect = Rect(0, 0, 0, 0)
        self._layout_dirty = True
        self._warned_no_screen = False

        # Subscribe to Engine Input Events
        self._dispatcher.subscribe(OnMouseEvent, self._on_mouse_event)
        self._dispatcher.subscribe(OnRawKeyEvent, self._on_key_event)
        self._dispatcher.subscribe(WindowResizeEvent, self._on_resize_event)

    def add_element(self, element: UIElement) -> None:
        """Add a root-level UI element."""
        self._root_elements.append(element)
        self._layout_dirty = True

    def set_screen_size(self, width: int, height: int) -> None:
        """Tell the UI the size of the surface its roots lay out against.

        Called once at startup and again whenever the window is resized, so
        percentage- and anchor-based constraints resolve against the real
        drawable area.
        """
        new_rect = Rect(0, 0, width, height)
        if new_rect == self._screen_rect:
            return
        self._screen_rect = new_rect
        self._layout_dirty = True

    def invalidate_layout(self) -> None:
        """Force a layout pass on the next render.

        Call after mutating something a layout depends on but the manager
        cannot see -- a label's text, an element's `visible` flag, a
        container's child list.
        """
        self._layout_dirty = True

    def update(self, dt: float) -> None:
        """Update all managed UI elements."""
        for element in self._root_elements:
            element.update(dt)

    def render(self, renderer: UIRenderer) -> None:
        """Draw the entire UI stack using the abstract renderer."""
        if self._layout_dirty:
            self._run_layout(renderer)
            self._layout_dirty = False

        for element in self._root_elements:
            if element.visible:
                element.render(renderer)

    def _run_layout(self, renderer: UIRenderer) -> None:
        """Lay every root out against the current screen rect."""
        if self._screen_rect.width <= 0 or self._screen_rect.height <= 0:
            has_constraints = any(
                self._subtree_has_constraints(el) for el in self._root_elements
            )
            if has_constraints and not self._warned_no_screen:
                logger.warning(
                    "UI layout skipped: screen size unknown. Call "
                    "UIManager.set_screen_size() before adding constrained "
                    "elements."
                )
                self._warned_no_screen = True
            return

        for element in self._root_elements:
            element.layout(self._screen_rect, renderer)

    @staticmethod
    def _subtree_has_constraints(element: UIElement) -> bool:
        """Report whether `element` or any descendant carries constraints."""
        if element.constraints is not None:
            return True
        return any(
            UIManager._subtree_has_constraints(child) for child in element.children
        )

    def set_focus(self, element: UIElement | None) -> None:
        """Set the focused element.

        Args:
            element: Element to focus, or None to clear focus.
        """
        if self._focused_element is element:
            return

        # Notify old element of focus lost
        if self._focused_element:
            self._focused_element.handle_event(UIEventType.FOCUS_LOST, Vector2(0, 0), 0)

        self._focused_element = element

        # Notify new element of focus gained
        if self._focused_element:
            self._focused_element.handle_event(
                UIEventType.FOCUS_GAINED, Vector2(0, 0), 0
            )

    @property
    def focused_element(self) -> UIElement | None:
        """Get the currently focused element."""
        return self._focused_element

    def _on_mouse_event(self, event: OnMouseEvent) -> None:
        """Handle engine mouse events and route them to UI elements."""
        # Map Engine Event -> UI Event Type
        if event.is_motion:
            event_type = UIEventType.MOUSE_MOVE
        elif event.is_down:
            event_type = UIEventType.MOUSE_DOWN
        else:
            event_type = UIEventType.MOUSE_UP

        # Convert tuple pos to Vector2
        pos = Vector2(event.position[0], event.position[1])

        # On click, track focus changes
        clicked_element: UIElement | None = None

        # Iterate in reverse (Front-to-Back) to find who clicks first
        for element in reversed(self._root_elements):
            if element.handle_event(event_type, pos, event.button):
                if event_type == UIEventType.MOUSE_DOWN:
                    clicked_element = element
                break

        # Update focus on mouse down
        if event_type == UIEventType.MOUSE_DOWN:
            self.set_focus(clicked_element)

    def _on_key_event(self, event: OnRawKeyEvent) -> None:
        """Handle keyboard events and route to focused element."""
        if self._focused_element is None:
            return

        event_type = UIEventType.KEY_DOWN if event.is_down else UIEventType.KEY_UP

        # Route to focused element
        self._focused_element.handle_event(event_type, Vector2(0, 0), event.key_code)

    def _on_resize_event(self, event: WindowResizeEvent) -> None:
        """Re-lay the UI out against the new window size."""
        self.set_screen_size(event.width, event.height)
