"""Concrete implementation of the event dispatcher."""

from __future__ import annotations

import queue
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeVar

from pyguara.events.protocols import Event
from pyguara.events.types import ErrorHandlingStrategy, EventHandler

if TYPE_CHECKING:
    from pyguara.log import EngineLogger

# `pyguara.log` imports this package at runtime -- its OnLogEvent and
# OnExceptionEvent inherit the Event protocol -- so `events` must not import
# `log` at module scope or the two packages deadlock on first import. Events
# are the more foundational of the two: log depends on events, and the
# dispatcher merely happens to log. The default logger is therefore resolved
# lazily, inside __init__, and EngineLogger is a type-only import.

E = TypeVar("E", bound=Event)

DEFAULT_QUEUE_WARNING_THRESHOLD = 10000
DEFAULT_MAX_HISTORY_SIZE = 1000


@dataclass
class HandlerRecord:
    """One subscription: the callback plus how and when it should run.

    Attributes:
        callback: Receives the event. Returning False stops propagation.
        priority: Higher runs first.
        filter_func: Optional predicate; the callback runs only if it passes.
        owner: Whatever registered this, for bulk teardown. Held as an id
            rather than a reference so a subscription never keeps its owner
            alive -- a scene that leaks its handlers should not also leak
            itself.
        once: True if the subscription removes itself after one delivery.
    """

    callback: Callable[[Any], bool | None]
    priority: int
    filter_func: Callable[[Any], bool] | None
    owner: int | None = None
    once: bool = False


class EventDispatcher:
    """Routes events to subscribers, with priority, filtering and queueing.

    Subscription is by type, and dispatch walks the event's MRO: a handler
    subscribed to a base class receives every subclass too. Handlers from the
    whole MRO merge into one priority-ordered pass, so priority governs call
    order regardless of which class in the hierarchy a handler subscribed to.
    Subscribing to `object` therefore receives everything.

    Thread safety:
        `queue_event()` is safe to call from any thread. Everything else --
        `dispatch()`, `subscribe()`, `unsubscribe()`, `clear_subscribers()` --
        must run on the main thread. Background threads queue; the main loop
        drains via `process_queue()`.
    """

    def __init__(
        self,
        logger: EngineLogger | None = None,
        error_strategy: ErrorHandlingStrategy = ErrorHandlingStrategy.RAISE,
        queue_warning_threshold: int = DEFAULT_QUEUE_WARNING_THRESHOLD,
        enable_history: bool = False,
        max_history_size: int = DEFAULT_MAX_HISTORY_SIZE,
    ) -> None:
        """Initialise a dispatcher with no subscribers.

        Args:
            logger: Where handler errors and queue warnings go. Defaults to
                the shared logging accessor, so the dispatcher always logs
                somewhere even when built before bootstrap wires anything.
            error_strategy: What to do when a handler or filter raises.
                RAISE fails fast in development; LOG degrades gracefully in
                production.
            queue_warning_threshold: Queue depth that triggers a warning,
                as an early signal of an event death spiral.
            enable_history: Record dispatched events for `get_history()`. A
                devtool and test feature; off by default so the hot path
                never pays for it.
            max_history_size: How many events history retains. Backed by a
                bounded deque, so enabling history cannot grow without bound.
        """
        self._listeners: defaultdict[type[Event], list[HandlerRecord]] = defaultdict(
            list
        )
        # type(event) -> its MRO's handlers, merged and priority-sorted.
        # dispatch() is the engine's hottest path; without this it rebuilt and
        # re-sorted that list on every single call. Dropped whenever the
        # subscription set changes.
        self._resolved: dict[type[Event], list[HandlerRecord]] = {}

        self._event_queue: queue.Queue[Event] = queue.Queue()
        # (remaining seconds, event) for `dispatch_after`. A countdown
        # rather than a deadline, so the caller's clock decides what a
        # second is -- see `advance()`.
        self._delayed: list[tuple[float, Event]] = []

        self._enable_history = enable_history
        self._max_history_size = max_history_size
        self._event_history: deque[Event] = deque(maxlen=max_history_size)
        if logger is None:
            from pyguara.log import get_logger

            logger = get_logger(__name__)
        self._logger = logger
        self._error_strategy = error_strategy
        self._queue_warning_threshold = queue_warning_threshold

    def subscribe(
        self,
        event_type: type[E],
        handler: EventHandler[E],
        priority: int = 0,
        filter_func: Callable[[E], bool] | None = None,
        owner: object | None = None,
        once: bool = False,
    ) -> None:
        """Register a handler for an event type and its subclasses.

        The same callable may be subscribed more than once -- with different
        priorities or filters, say -- and will then run once per subscription.

        Args:
            event_type: The class to listen for. Subclasses match too.
            handler: Receives the event. Returning False stops propagation to
                lower-priority handlers.
            priority: Higher runs first. Ties keep subscription order.
            filter_func: Optional predicate; the handler runs only if it
                returns True.
            owner: Anything at all -- a scene, a system -- that
                `clear_subscribers(owner=...)` can later drop in one call.
                The dispatcher keeps only its `id()`, never a reference, so
                subscribing cannot keep the owner alive.
            once: Remove the subscription after its first delivery. The
                handler still runs; it simply does not run again.
        """
        record = HandlerRecord(
            callback=handler,
            priority=priority,
            filter_func=filter_func,
            owner=None if owner is None else id(owner),
            once=once,
        )
        self._listeners[event_type].append(record)
        self._resolved.clear()

    def subscribe_once(
        self,
        event_type: type[E],
        handler: EventHandler[E],
        priority: int = 0,
        filter_func: Callable[[E], bool] | None = None,
        owner: object | None = None,
    ) -> None:
        """Register a handler that fires at most once.

        For the "when the door first opens" shape, which otherwise becomes a
        handler whose whole body is a `self._already_fired` guard.

        A filtered one-shot survives until the filter actually passes: the
        subscription is spent by *delivery*, not by the event merely being
        dispatched. Waiting for `OnDamage` from one specific entity would be
        useless otherwise.

        Args:
            event_type: The class to listen for. Subclasses match too.
            handler: Receives the event, once.
            priority: Higher runs first. Ties keep subscription order.
            filter_func: Optional predicate; the handler runs, and the
                subscription is spent, only when it returns True.
            owner: For bulk teardown; see `subscribe()`.
        """
        self.subscribe(
            event_type,
            handler,
            priority=priority,
            filter_func=filter_func,
            owner=owner,
            once=True,
        )

    def unsubscribe(self, event_type: type[E], handler: EventHandler[E]) -> None:
        """Remove every subscription of a handler for an event type.

        Removes all of them if the handler was subscribed more than once.
        Unsubscribing something that was never subscribed is a no-op.

        Args:
            event_type: The class the handler was registered against. Must be
                the same class used to subscribe, not a subclass.
            handler: The callable to remove.
        """
        records = self._listeners.get(event_type)
        if records is None:
            return
        self._listeners[event_type] = [r for r in records if r.callback != handler]
        self._resolved.clear()

    def clear_subscribers(
        self, event_type: type[Event] | None = None, owner: object | None = None
    ) -> None:
        """Remove subscribers, by event type, by owner, or all of them.

        `owner` is the teardown half of `subscribe(owner=...)`: a scene
        drops every handler it registered in one call, without tracking
        them or knowing what they were. The alternative -- remembering each
        `(event_type, handler)` pair to unsubscribe in `on_exit` -- is what
        leaks a handler the moment anyone forgets one, and a leaked handler
        does not merely linger: it double-fires after a scene reload.

        Given both, only subscriptions matching *both* are removed.

        Args:
            event_type: The class to clear. None means any.
            owner: The owner to clear. None means any, **not** "the
                unowned ones" -- pass the owner to be selective.
        """
        if owner is not None:
            owner_id = id(owner)
            types = [event_type] if event_type is not None else list(self._listeners)
            for cls in types:
                records = self._listeners.get(cls)
                if records is None:
                    continue
                self._listeners[cls] = [r for r in records if r.owner != owner_id]
        elif event_type is not None:
            self._listeners.pop(event_type, None)
        else:
            self._listeners.clear()
        self._resolved.clear()

    def dispatch(self, event: Event) -> bool:
        """Deliver an event to its subscribers immediately, on this thread.

        Handlers run in priority order, merged across the event's whole MRO.
        The handler list is snapshotted first, so a handler that subscribes or
        unsubscribes affects the next dispatch, not this one.

        Args:
            event: The event to deliver.

        Returns:
            True if every applicable handler ran; False if one returned False
            and consumed the event, stopping lower-priority handlers.

        Warning:
            Runs on the calling thread. Use `queue_event()` from background
            threads.
        """
        self._record_history(event)
        return self._process_handlers(self._resolve_handlers(type(event)), event)

    def queue_event(self, event: Event) -> None:
        """Queue an event for the next `process_queue()`. Thread-safe.

        Args:
            event: The event to queue.
        """
        self._event_queue.put(event)

    def dispatch_after(self, delay: float, event: Event) -> None:
        """Dispatch `event` once `delay` seconds of game time have passed.

        For "spawn the reward half a second after the boss dies", which
        otherwise becomes a hand-rolled timer on some system that had no
        other reason to exist.

        The delay is measured in whatever time `advance()` is fed, which
        `Application` scales by `time_scale` and zeroes while paused. A
        pending event therefore waits out a pause and runs at half speed in
        slow motion, rather than firing into a frozen world.

        A delay of zero or less dispatches on the next `advance()`, not
        immediately -- use `dispatch()` to deliver now.

        Args:
            delay: Seconds of game time to wait.
            event: The event to dispatch when the delay elapses.
        """
        self._delayed.append((delay, event))

    def advance(self, dt: float) -> None:
        """Advance pending `dispatch_after` timers and fire what is due.

        Called once per frame by `Application`, with the same scaled delta
        the physics accumulator gets.

        An event whose handler schedules another delayed event does not
        also fire this call: the new one is appended to the list being
        rebuilt, so it starts its own delay from the next `advance()`. That
        is what stops a zero-delay chain from spinning inside one frame.

        Args:
            dt: Seconds of game time elapsed since the last call.
        """
        if not self._delayed:
            return

        pending = self._delayed
        self._delayed = []
        due: list[Event] = []
        for remaining, event in pending:
            remaining -= dt
            if remaining <= 0.0:
                due.append(event)
            else:
                self._delayed.append((remaining, event))

        for event in due:
            self.dispatch(event)

    def process_queue(
        self, max_time_ms: float | None = None, max_events: int | None = None
    ) -> int:
        """Drain queued events, within optional time and count budgets.

        Call once per frame from the main loop. Only events already queued
        when the call began are considered; anything a handler queues waits
        for the next frame, as does anything left over when a budget runs out.

        Args:
            max_time_ms: Time budget in milliseconds. None means no limit.
            max_events: Maximum events to process. None means no limit.

        Returns:
            The number of events dispatched.
        """
        queue_size = self._event_queue.qsize()

        if queue_size > self._queue_warning_threshold and self._logger:
            self._logger.warning(
                f"Event queue size ({queue_size}) exceeds threshold "
                f"({self._queue_warning_threshold}). Possible event death spiral."
            )

        count = queue_size if max_events is None else min(queue_size, max_events)
        start_time = time.perf_counter() if max_time_ms is not None else None
        processed = 0

        for _ in range(count):
            if start_time is not None and max_time_ms is not None:
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                if elapsed_ms >= max_time_ms:
                    break

            try:
                event = self._event_queue.get_nowait()
            except queue.Empty:
                break
            self.dispatch(event)
            processed += 1

        return processed

    def get_history(self, event_type: type[Event] | None = None) -> list[Event]:
        """Return recorded events, oldest first.

        Empty unless the dispatcher was built with `enable_history=True`.

        Args:
            event_type: If given, return only events of this type or a
                subclass of it.

        Returns:
            A snapshot list of the retained events.
        """
        if event_type is not None:
            return [e for e in self._event_history if isinstance(e, event_type)]
        return list(self._event_history)

    def _resolve_handlers(self, event_type: type[Event]) -> list[HandlerRecord]:
        """Return the priority-ordered handlers for an event type, memoised.

        Args:
            event_type: The concrete class of the event being dispatched.

        Returns:
            Handlers from every class in the MRO, highest priority first.
            Ties keep MRO order, so a subclass handler precedes a base one.
        """
        cached = self._resolved.get(event_type)
        if cached is not None:
            return cached

        handlers: list[HandlerRecord] = []
        for cls in event_type.__mro__:
            handlers.extend(self._listeners.get(cls, ()))
        handlers.sort(key=lambda r: r.priority, reverse=True)

        self._resolved[event_type] = handlers
        return handlers

    def _process_handlers(self, records: list[HandlerRecord], event: Event) -> bool:
        """Run handlers in order until one consumes the event.

        Args:
            records: Handlers to run, already in priority order.
            event: The event to pass to each handler.

        Returns:
            True if the pass completed; False if a handler returned False.

        Raises:
            Exception: Whatever a handler or filter raised, if the error
                strategy is RAISE.
        """
        for record in records:
            try:
                if record.filter_func is not None and not record.filter_func(event):
                    continue
                if record.once:
                    # Retired *before* the callback runs, so a handler that
                    # dispatches the same event type again -- or raises --
                    # cannot re-enter this subscription.
                    self._retire(record)
                if record.callback(event) is False:
                    return False
            except Exception as error:
                # Filters are user code too, so they get the same treatment as
                # handlers rather than escaping the configured strategy.
                if not self._handle_error(record, event, error):
                    raise
        return True

    def _retire(self, record: HandlerRecord) -> None:
        """Drop a spent one-shot subscription.

        Searched by identity across the listener lists, because the record
        reached `_process_handlers` through the resolved cache and no
        longer knows which event type it was registered against -- a
        subclass dispatch pulls in handlers registered on every base.

        Args:
            record: The subscription to remove.
        """
        for records in self._listeners.values():
            for i, existing in enumerate(records):
                if existing is record:
                    del records[i]
                    self._resolved.clear()
                    return

    def _handle_error(
        self, record: HandlerRecord, event: Event, error: Exception
    ) -> bool:
        """Apply the configured error strategy to a failed handler or filter.

        Args:
            record: The subscription that raised.
            event: The event being dispatched.
            error: The exception that was raised.

        Returns:
            True if dispatch should continue with the next handler, False if
            the exception should propagate.
        """
        if self._error_strategy is ErrorHandlingStrategy.IGNORE:
            return True

        handler_name = getattr(record.callback, "__name__", str(record.callback))
        error_msg = (
            f"Error in event handler '{handler_name}' "
            f"for event type '{type(event).__name__}': {error}"
        )
        if self._logger:
            self._logger.error(error_msg, exc_info=True)

        return self._error_strategy is ErrorHandlingStrategy.LOG

    def _record_history(self, event: Event) -> None:
        """Append an event to history when history is enabled.

        Args:
            event: The event being dispatched.
        """
        if self._enable_history:
            self._event_history.append(event)
