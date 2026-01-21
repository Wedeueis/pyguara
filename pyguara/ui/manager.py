"""UI Manager and event integration."""

from typing import List, Optional

from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.events import OnMouseEvent, OnRawKeyEvent
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.base import UIElement
from pyguara.ui.types import UIEventType


class UIManager:
    """Manages the UI Scene Graph and routes engine events."""

    def __init__(self, dispatcher: EventDispatcher) -> None:
        """Initialize the UI manager and subscribe to input events."""
        self._root_elements: List[UIElement] = []
        self._dispatcher = dispatcher
        self._focused_element: Optional[UIElement] = None

        # Subscribe to Engine Input Events
        self._dispatcher.subscribe(OnMouseEvent, self._on_mouse_event)
        self._dispatcher.subscribe(OnRawKeyEvent, self._on_key_event)

    def add_element(self, element: UIElement) -> None:
        """Add a root-level UI element."""
        self._root_elements.append(element)

    def update(self, dt: float) -> None:
        """Update all managed UI elements."""
        for element in self._root_elements:
            element.update(dt)

    def render(self, renderer: UIRenderer) -> None:
        """Draw the entire UI stack using the abstract renderer."""
        for element in self._root_elements:
            if element.visible:
                element.render(renderer)

    def set_focus(self, element: Optional[UIElement]) -> None:
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
    def focused_element(self) -> Optional[UIElement]:
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
        clicked_element: Optional[UIElement] = None

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
