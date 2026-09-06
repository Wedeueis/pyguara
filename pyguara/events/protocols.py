"""Core protocols defining the contracts for the Event System."""

from __future__ import annotations

from typing import Any, Callable, Protocol, TypeVar, runtime_checkable

from pyguara.events.types import EventHandler

E = TypeVar("E", bound="Event")


@runtime_checkable
class Event(Protocol):
    """Structural contract every event satisfies.

    A Protocol rather than a base class, so an event can be a plain dataclass
    without inheriting anything. Prefer `field(default_factory=time.time)` for
    the timestamp over a sentinel checked in `__post_init__`, which cannot
    express a genuine timestamp of 0.0.

    Attributes:
        timestamp: Unix time the event was created.
        source: Whatever raised the event, if it identified itself.
    """

    timestamp: float
    source: Any


@runtime_checkable
class IEventDispatcher(Protocol):
    """Interface for event system management.

    Responsible for routing events to registered handlers based on type.
    """

    def dispatch(self, event: Event) -> bool:
        """Deliver an event to its subscribers immediately, on this thread.

        Args:
            event: The event to broadcast.

        Returns:
            True if every applicable handler ran; False if one consumed the
            event by returning False.
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

    def process_queue(
        self, max_time_ms: float | None = None, max_events: int | None = None
    ) -> int:
        """
        Flush the event queue and dispatch pending events with optional limits.

        This should be called once per frame by the Application main loop.

        Args:
            max_time_ms: Optional time budget in milliseconds.
            max_events: Optional maximum number of events to process.

        Returns:
            Number of events processed.
        """
        ...

    def subscribe(
        self,
        event_type: type[E],
        handler: EventHandler[E],
        priority: int = 0,
        filter_func: Callable[[E], bool] | None = None,
    ) -> None:
        """Subscribe to an event type and its subclasses.

        Args:
            event_type: The class to listen for. Subclasses match too.
            handler: Receives the event. Returning False stops propagation.
            priority: Higher runs first. Ties keep subscription order.
            filter_func: Optional predicate; the handler runs only if it
                returns True.
        """
        ...

    def unsubscribe(self, event_type: type[E], handler: EventHandler[E]) -> None:
        """Unsubscribe from an event type.

        Args:
            event_type: The class of the event to stop listening for.
            handler: The specific callable to remove.
        """
        ...

    def clear_subscribers(self, event_type: type[Event] | None = None) -> None:
        """Clear subscribers for an event type or all events.

        Args:
            event_type: If provided, clears only that event's handlers.
                        If None, clears the entire dispatcher.
        """
        ...
