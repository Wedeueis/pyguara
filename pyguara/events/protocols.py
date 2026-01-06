"""Core protocols defining the contracts for the Event System."""

from typing import Any, Protocol, Optional, Type, TypeVar, runtime_checkable
from pyguara.events.types import EventHandler

# Define a generic type variable bound to the Event protocol
E = TypeVar("E", bound="Event")


@runtime_checkable
class Event(Protocol):
    """Core event protocol for type checking.

    All concrete events should implement these fields.
    Using a Protocol allows events to be simple dataclasses or complex objects.
    """

    @property
    def timestamp(self) -> float:
        """Get the time the event occurred."""
        ...

    @property
    def source(self) -> Any:
        """Get the object that triggered the event."""
        ...


@runtime_checkable
class IEventDispatcher(Protocol):
    """Interface for event system management.

    Responsible for routing events to registered handlers based on type.
    """

    def dispatch(self, event: Event) -> None:
        """Dispatch an event to all subscribers immediately (Synchronous).

        Args:
            event: The event instance to broadcast.
        """
        ...

    def queue_event(self, event: Event) -> None:
        """
        Thread-Safe: Queue an event to be dispatched on the next frame.

        Use this when firing events from background threads (e.g., Network, Loader)
        to ensure handlers run on the Main Thread.

        Args:
            event: The event to queue.
        """
        ...

    def process_queue(self) -> None:
        """
        Flush the event queue and dispatch pending events.

        This should be called once per frame by the Application main loop.
        """
        ...

    def subscribe(
        self, event_type: Type[E], handler: EventHandler[E], priority: int = 0
    ) -> None:
        """Subscribe to an event type.

        Args:
            event_type: The class of the event to listen for.
            handler: A callable that will receive the event.
            priority: Execution order (Higher runs first). Defaults to 0.
        """
        ...

    def unsubscribe(self, event_type: Type[E], handler: EventHandler[E]) -> None:
        """Unsubscribe from an event type.

        Args:
            event_type: The class of the event to stop listening for.
            handler: The specific callable to remove.
        """
        ...

    def clear_subscribers(self, event_type: Optional[Type[Event]] = None) -> None:
        """Clear subscribers for an event type or all events.

        Args:
            event_type: If provided, clears only that event's handlers.
                        If None, clears the entire dispatcher.
        """
        ...
