"""UI Manager and event integration."""

from typing import List

from pyguara.common.types import Vector2
from pyguara.events.dispatcher import EventDispatcher
from pyguara.input.events import OnMouseEvent
from pyguara.graphics.protocols import UIRenderer
from pyguara.ui.base import UIElement
from pyguara.ui.types import UIEventType


class UIManager:
    """Manages the UI Scene Graph and routes engine events."""

    def __init__(self, dispatcher: EventDispatcher) -> None:
        """Initialize the UI manager and subscribe to input events."""
        self._root_elements: List[UIElement] = []
        self._dispatcher = dispatcher

        # Subscribe to Engine Input Events
        self._dispatcher.subscribe(OnMouseEvent, self._on_mouse_event)

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

        # Iterate in reverse (Front-to-Back) to find who clicks first
        for element in reversed(self._root_elements):
            if element.handle_event(event_type, pos, event.button):
                # If UI consumed it, we could signal to stop propagation
                # But typically UIManager is a peer listener.
                # If we need to block game input, we'd use a shared state flag.
                break
