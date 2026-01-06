"""Concrete implementation of the Event Dispatcher."""

import logging
import queue
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, DefaultDict, List, Optional, Type, TypeVar

from pyguara.events.protocols import Event, IEventDispatcher
from pyguara.events.types import EventHandler

E = TypeVar("E", bound=Event)


@dataclass
class HandlerRecord:
    """Internal wrapper for registered listeners."""

    callback: Callable[[Any], Optional[bool]]
    priority: int
    filter_func: Optional[Callable[[Any], bool]]


class EventDispatcher(IEventDispatcher):
    """Advanced event dispatcher with filtering, priority, and thread-safety support."""

    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        """Initialize the dispatcher."""
        self._listeners: DefaultDict[Type[Event], List[HandlerRecord]] = defaultdict(
            list
        )
        self._global_listeners: List[HandlerRecord] = []

        # Thread-safe queue for events from background threads
        self._event_queue: queue.Queue[Event] = queue.Queue()

        self._event_history: List[Event] = []
        self._max_history_size: int = 1000
        self._logger = logger

    def subscribe(
        self,
        event_type: Type[E],
        handler: EventHandler[E],
        priority: int = 0,
        filter_func: Optional[Callable[[E], bool]] = None,
    ) -> None:
        """Subscribe to a specific event type."""
        record = HandlerRecord(
            callback=handler, priority=priority, filter_func=filter_func
        )
        target_list = self._listeners[event_type]
        target_list.append(record)
        target_list.sort(key=lambda r: r.priority, reverse=True)

    def subscribe_global(
        self,
        handler: EventHandler[Event],
        priority: int = 0,
        filter_func: Optional[Callable[[Event], bool]] = None,
    ) -> None:
        """Subscribe to ALL events."""
        record = HandlerRecord(
            callback=handler, priority=priority, filter_func=filter_func
        )
        self._global_listeners.append(record)
        self._global_listeners.sort(key=lambda r: r.priority, reverse=True)

    def unsubscribe(self, event_type: Type[E], handler: EventHandler[E]) -> None:
        """Unsubscribe a specific handler."""
        if event_type in self._listeners:
            self._listeners[event_type] = [
                r for r in self._listeners[event_type] if r.callback != handler
            ]

    def clear_subscribers(self, event_type: Optional[Type[Event]] = None) -> None:
        """Clear subscribers."""
        if event_type:
            if event_type in self._listeners:
                del self._listeners[event_type]
        else:
            self._listeners.clear()
            self._global_listeners.clear()

    def dispatch(self, event: Event) -> None:
        """
        Dispatch an event immediately to all subscribers.

        WARNING: This runs on the calling thread. For background threads,
        use queue_event() instead.
        """
        self._record_history(event)

        # Phase A: Specific Listeners
        event_type = type(event)
        specific_handlers = self._listeners.get(event_type, [])

        if not self._process_handlers(specific_handlers, event):
            return

        # Phase B: Global Listeners
        self._process_handlers(self._global_listeners, event)

    def queue_event(self, event: Event) -> None:
        """
        Queue an event to be dispatched on the main thread later.

        This method is thread-safe and non-blocking.
        """
        self._event_queue.put(event)

    def process_queue(self) -> None:
        """
        Process all currently queued events.

        Call this in your main game loop (e.g. at the start of update()).
        """
        while not self._event_queue.empty():
            try:
                event = self._event_queue.get_nowait()
                self.dispatch(event)
            except queue.Empty:
                break

    def _process_handlers(self, records: List[HandlerRecord], event: Event) -> bool:
        """Process a list of handlers.

        Returns:
            bool: False if a handler stopped propagation, True otherwise.
        """
        for record in records:
            if record.filter_func and not record.filter_func(event):
                continue

            try:
                if self._logger:
                    self._logger.debug(f"Dispatching {type(event).__name__}")

                result = record.callback(event)

                if result is False:
                    return False

            except Exception as e:
                if self._logger:
                    self._logger.error(f"Error in listener: {e}")

        return True

    def _record_history(self, event: Event) -> None:
        """Add event to history buffer."""
        self._event_history.append(event)
        if len(self._event_history) > self._max_history_size:
            self._event_history.pop(0)

    def get_history(self, event_type: Optional[Type[Event]] = None) -> List[Event]:
        """Retrieve recent events, optionally filtered."""
        if event_type:
            return [e for e in self._event_history if isinstance(e, event_type)]
        return list(self._event_history)
