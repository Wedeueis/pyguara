"""Concrete implementation of the Event Dispatcher."""

import logging
import queue
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, DefaultDict, List, Optional, Type, TypeVar

from pyguara.events.protocols import Event, IEventDispatcher
from pyguara.events.types import EventHandler, ErrorHandlingStrategy

E = TypeVar("E", bound=Event)


@dataclass
class HandlerRecord:
    """DTO with information to handle the event call."""

    callback: Callable[[Any], Optional[bool]]
    priority: int
    filter_func: Optional[Callable[[Any], bool]]


class EventDispatcher(IEventDispatcher):
    """Advanced event dispatcher with filtering, priority, and thread-safety support."""

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        error_strategy: ErrorHandlingStrategy = ErrorHandlingStrategy.RAISE,
    ) -> None:
        """Initialize the Event Dispatcher.

        Args:
            logger: Optional logger for error reporting.
            error_strategy: How to handle errors in event handlers. Defaults to RAISE
                for fail-fast behavior in development. Use LOG for production
                graceful degradation.
        """
        self._listeners: DefaultDict[Type[Event], List[HandlerRecord]] = defaultdict(
            list
        )
        self._global_listeners: List[HandlerRecord] = []

        # Thread-safe queue
        self._event_queue: queue.Queue[Event] = queue.Queue()

        self._event_history: List[Event] = []
        self._max_history_size: int = 1000
        self._logger = logger
        self._error_strategy = error_strategy

    def subscribe(
        self,
        event_type: Type[E],
        handler: EventHandler[E],
        priority: int = 0,
        filter_func: Optional[Callable[[E], bool]] = None,
    ) -> None:
        """Subscribe a handler to a specific event type."""
        record = HandlerRecord(
            callback=handler, priority=priority, filter_func=filter_func
        )
        target_list = self._listeners[event_type]
        target_list.append(record)
        target_list.sort(key=lambda r: r.priority, reverse=True)

    def dispatch(self, event: Event) -> None:
        """
        Dispatch an event immediately to all subscribers (Synchronous).

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
        """Queue event for next frame (Thread-Safe)."""
        self._event_queue.put(event)

    def process_queue(self) -> None:
        """Safely process currently queued events."""
        count = self._event_queue.qsize()
        for _ in range(count):
            try:
                event = self._event_queue.get_nowait()
                self.dispatch(event)
            except queue.Empty:
                break

    def _process_handlers(self, records: List[HandlerRecord], event: Event) -> bool:
        for record in records:
            if record.filter_func and not record.filter_func(event):
                continue
            try:
                result = record.callback(event)
                if result is False:
                    return False
            except Exception as e:
                # Handle error based on configured strategy
                event_type = type(event).__name__
                handler_name = getattr(
                    record.callback, "__name__", str(record.callback)
                )

                error_msg = (
                    f"Error in event handler '{handler_name}' "
                    f"for event type '{event_type}': {e}"
                )

                if self._error_strategy == ErrorHandlingStrategy.IGNORE:
                    # Silently ignore (not recommended)
                    pass
                elif self._error_strategy == ErrorHandlingStrategy.LOG:
                    # Log and continue
                    if self._logger:
                        self._logger.error(error_msg, exc_info=True)
                else:  # ErrorHandlingStrategy.RAISE
                    # Log and re-raise
                    if self._logger:
                        self._logger.error(error_msg, exc_info=True)
                    raise
        return True

    def unsubscribe(self, event_type: Type[E], handler: EventHandler[E]) -> None:
        """Remove a handler of an event type listeners."""
        if event_type in self._listeners:
            self._listeners[event_type] = [
                r for r in self._listeners[event_type] if r.callback != handler
            ]

    def clear_subscribers(self, event_type: Optional[Type[Event]] = None) -> None:
        """Clear all listeners or all listeners of a specific event type."""
        if event_type:
            if event_type in self._listeners:
                del self._listeners[event_type]
        else:
            self._listeners.clear()
            self._global_listeners.clear()

    def _record_history(self, event: Event) -> None:
        """Register an event in history."""
        self._event_history.append(event)
        if len(self._event_history) > self._max_history_size:
            self._event_history.pop(0)

    def get_history(self, event_type: Optional[Type[Event]] = None) -> List[Event]:
        """Return all history records or all history records of an event type."""
        if event_type:
            return [e for e in self._event_history if isinstance(e, event_type)]
        return list(self._event_history)
