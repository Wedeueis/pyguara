from dataclasses import dataclass
from typing import Any

import pytest

from pyguara.events.dispatcher import EventDispatcher
from pyguara.events.protocols import Event
from pyguara.events.types import ErrorHandlingStrategy


@dataclass
class CustomEvent(Event):
    data: str
    timestamp: float = 0.0
    source: object = None


def test_subscribe_and_dispatch(event_dispatcher) -> None:
    received = []

    def handler(event: CustomEvent):
        received.append(event.data)

    event_dispatcher.subscribe(CustomEvent, handler)
    event_dispatcher.dispatch(CustomEvent(data="hello"))

    assert len(received) == 1
    assert received[0] == "hello"


def test_unsubscribe(event_dispatcher) -> None:
    received = []

    def handler(event: CustomEvent):
        received.append(event.data)

    event_dispatcher.subscribe(CustomEvent, handler)
    event_dispatcher.unsubscribe(CustomEvent, handler)
    event_dispatcher.dispatch(CustomEvent(data="hello"))

    assert len(received) == 0


def test_priority(event_dispatcher) -> None:
    order = []

    def handler_low(e):
        order.append("low")

    def handler_high(e):
        order.append("high")

    event_dispatcher.subscribe(CustomEvent, handler_low, priority=1)
    event_dispatcher.subscribe(CustomEvent, handler_high, priority=10)

    event_dispatcher.dispatch(CustomEvent(data=""))

    assert order == ["high", "low"]


def test_event_queue(event_dispatcher) -> None:
    received = []

    def handler(e: Any) -> None:
        received.append(e.data)

    event_dispatcher.subscribe(CustomEvent, handler)

    # Queue event
    event_dispatcher.queue_event(CustomEvent(data="queued"))
    assert len(received) == 0  # Not processed yet

    # Process
    event_dispatcher.process_queue()
    assert len(received) == 1
    assert received[0] == "queued"


def test_event_filtering(event_dispatcher) -> None:
    received = []

    def handler(e: Any) -> None:
        received.append(e.data)

    # Only accept data="yes"
    event_dispatcher.subscribe(
        CustomEvent, handler, filter_func=lambda e: e.data == "yes"
    )

    event_dispatcher.dispatch(CustomEvent(data="no"))
    event_dispatcher.dispatch(CustomEvent(data="yes"))

    assert len(received) == 1
    assert received[0] == "yes"


def test_error_handling_strategy_raise():
    """Test that RAISE strategy re-raises exceptions."""
    import pytest
    import logging
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.events.types import ErrorHandlingStrategy

    logger = logging.getLogger("test")
    dispatcher = EventDispatcher(
        logger=logger, error_strategy=ErrorHandlingStrategy.RAISE
    )

    def failing_handler(e: CustomEvent) -> None:
        raise ValueError("Test error")

    dispatcher.subscribe(CustomEvent, failing_handler)

    # Should re-raise the exception
    with pytest.raises(ValueError, match="Test error"):
        dispatcher.dispatch(CustomEvent(data="test"))


def test_error_handling_strategy_log():
    """Test that LOG strategy logs and continues."""
    import logging
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.events.types import ErrorHandlingStrategy

    logger = logging.getLogger("test")
    dispatcher = EventDispatcher(
        logger=logger, error_strategy=ErrorHandlingStrategy.LOG
    )

    execution_order = []

    def failing_handler(e: CustomEvent) -> None:
        execution_order.append("failing")
        raise ValueError("Test error")

    def success_handler(e: CustomEvent) -> None:
        execution_order.append("success")

    dispatcher.subscribe(CustomEvent, failing_handler, priority=10)
    dispatcher.subscribe(CustomEvent, success_handler, priority=5)

    # Should log error and continue to next handler
    dispatcher.dispatch(CustomEvent(data="test"))

    # Both handlers should have been called
    assert execution_order == ["failing", "success"]


def test_error_handling_strategy_ignore():
    """Test that IGNORE strategy silently ignores errors."""
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.events.types import ErrorHandlingStrategy

    dispatcher = EventDispatcher(error_strategy=ErrorHandlingStrategy.IGNORE)

    execution_order = []

    def failing_handler(e: CustomEvent) -> None:
        execution_order.append("failing")
        raise ValueError("Test error")

    def success_handler(e: CustomEvent) -> None:
        execution_order.append("success")

    dispatcher.subscribe(CustomEvent, failing_handler, priority=10)
    dispatcher.subscribe(CustomEvent, success_handler, priority=5)

    # Should silently ignore error and continue
    dispatcher.dispatch(CustomEvent(data="test"))

    # Both handlers should have been called
    assert execution_order == ["failing", "success"]


def test_default_logger_emits_queue_overflow_warning_without_explicit_logger(caplog):
    """No logger passed in still logs (logging migration, ticket 16)."""
    import logging
    from pyguara.events.dispatcher import EventDispatcher

    dispatcher = EventDispatcher(queue_warning_threshold=0)
    dispatcher.queue_event(CustomEvent(data="overflow"))

    with caplog.at_level(logging.WARNING, logger="pyguara.events.dispatcher"):
        dispatcher.process_queue()

    assert any("exceeds threshold" in record.getMessage() for record in caplog.records)


def test_error_message_includes_context():
    """Test that error messages include handler and event type information."""
    import pytest
    import logging
    from pyguara.events.dispatcher import EventDispatcher
    from pyguara.events.types import ErrorHandlingStrategy
    from unittest.mock import MagicMock

    logger = MagicMock(spec=logging.Logger)
    dispatcher = EventDispatcher(
        logger=logger, error_strategy=ErrorHandlingStrategy.RAISE
    )

    def my_failing_handler(e: CustomEvent) -> None:
        raise ValueError("Test error")

    dispatcher.subscribe(CustomEvent, my_failing_handler)

    # Should log error with context
    with pytest.raises(ValueError):
        dispatcher.dispatch(CustomEvent(data="test"))

    # Verify logger was called with error message containing context
    logger.error.assert_called_once()
    error_msg = logger.error.call_args[0][0]
    assert "my_failing_handler" in error_msg
    assert "CustomEvent" in error_msg
    assert "Test error" in error_msg


# P1-009: Event Queue Safety Tests


def test_process_queue_max_events_limit():
    """Test that max_events parameter limits number of processed events."""
    from pyguara.events.dispatcher import EventDispatcher

    dispatcher = EventDispatcher()
    received = []

    def handler(e: CustomEvent) -> None:
        received.append(e.data)

    dispatcher.subscribe(CustomEvent, handler)

    # Queue 10 events
    for i in range(10):
        dispatcher.queue_event(CustomEvent(data=f"event_{i}"))

    # Process only 3
    processed = dispatcher.process_queue(max_events=3)

    assert processed == 3
    assert len(received) == 3
    assert received == ["event_0", "event_1", "event_2"]

    # Remaining events still in queue
    remaining = dispatcher.process_queue()
    assert remaining == 7
    assert len(received) == 10


def test_process_queue_time_budget():
    """Test that max_time_ms parameter enforces time budget."""
    import time
    from pyguara.events.dispatcher import EventDispatcher

    dispatcher = EventDispatcher()
    received = []

    def slow_handler(e: CustomEvent) -> None:
        # Each event takes ~2ms to process
        time.sleep(0.002)
        received.append(e.data)

    dispatcher.subscribe(CustomEvent, slow_handler)

    # Queue 20 events (would take ~40ms total)
    for i in range(20):
        dispatcher.queue_event(CustomEvent(data=f"event_{i}"))

    # Process with 10ms budget (should process ~5 events)
    processed = dispatcher.process_queue(max_time_ms=10.0)

    # Should have processed fewer than all events
    assert processed < 20
    assert len(received) == processed

    # Should have at least processed a few
    assert processed >= 2

    # Remaining events still in queue
    queue_size = dispatcher._event_queue.qsize()
    assert queue_size == 20 - processed


def test_process_queue_no_limits():
    """Test that process_queue with no limits processes all events."""
    from pyguara.events.dispatcher import EventDispatcher

    dispatcher = EventDispatcher()
    received = []

    def handler(e: CustomEvent) -> None:
        received.append(e.data)

    dispatcher.subscribe(CustomEvent, handler)

    # Queue 100 events
    for i in range(100):
        dispatcher.queue_event(CustomEvent(data=f"event_{i}"))

    # Process all with no limits
    processed = dispatcher.process_queue()

    assert processed == 100
    assert len(received) == 100
    assert dispatcher._event_queue.qsize() == 0


def test_process_queue_empty():
    """Test that process_queue handles empty queue correctly."""
    from pyguara.events.dispatcher import EventDispatcher

    dispatcher = EventDispatcher()

    processed = dispatcher.process_queue(max_time_ms=5.0, max_events=10)

    assert processed == 0


def test_queue_size_warning_threshold():
    """Test that large queue size triggers warning log."""
    import logging
    from unittest.mock import MagicMock
    from pyguara.events.dispatcher import EventDispatcher

    logger = MagicMock(spec=logging.Logger)
    dispatcher = EventDispatcher(logger=logger, queue_warning_threshold=100)

    # Queue events below threshold - no warning
    for i in range(50):
        dispatcher.queue_event(CustomEvent(data=f"event_{i}"))

    dispatcher.process_queue(max_events=0)  # Don't process any
    logger.warning.assert_not_called()

    # Queue more to exceed threshold
    for i in range(60):
        dispatcher.queue_event(CustomEvent(data=f"event_{i}"))

    dispatcher.process_queue(max_events=0)  # Don't process any
    logger.warning.assert_called_once()

    # Check warning message
    warning_msg = logger.warning.call_args[0][0]
    assert "110" in warning_msg  # Queue size
    assert "100" in warning_msg  # Threshold
    assert "death spiral" in warning_msg.lower()


def test_queue_size_warning_custom_threshold():
    """Test custom queue warning threshold."""
    import logging
    from unittest.mock import MagicMock
    from pyguara.events.dispatcher import EventDispatcher

    logger = MagicMock(spec=logging.Logger)
    dispatcher = EventDispatcher(logger=logger, queue_warning_threshold=5)

    # Queue 10 events (exceeds threshold of 5)
    for i in range(10):
        dispatcher.queue_event(CustomEvent(data=f"event_{i}"))

    dispatcher.process_queue(max_events=0)
    logger.warning.assert_called_once()


def test_process_queue_mixed_limits():
    """Test that both max_time_ms and max_events work together."""
    import time
    from pyguara.events.dispatcher import EventDispatcher

    dispatcher = EventDispatcher()
    received = []

    def slow_handler(e: CustomEvent) -> None:
        time.sleep(0.001)  # 1ms per event
        received.append(e.data)

    dispatcher.subscribe(CustomEvent, handler=slow_handler)

    # Queue 100 events
    for i in range(100):
        dispatcher.queue_event(CustomEvent(data=f"event_{i}"))

    # Process with both limits (should hit whichever comes first)
    processed = dispatcher.process_queue(max_time_ms=20.0, max_events=5)

    # Should have hit the max_events limit
    assert processed == 5
    assert len(received) == 5

    # Remaining events in queue
    assert dispatcher._event_queue.qsize() == 95


def test_unprocessed_events_remain_in_queue():
    """Test that unprocessed events persist across multiple frames."""
    from pyguara.events.dispatcher import EventDispatcher

    dispatcher = EventDispatcher()
    received = []

    def handler(e: CustomEvent) -> None:
        received.append(e.data)

    dispatcher.subscribe(CustomEvent, handler)

    # Queue 20 events
    for i in range(20):
        dispatcher.queue_event(CustomEvent(data=f"event_{i}"))

    # Frame 1: Process 5 events
    processed = dispatcher.process_queue(max_events=5)
    assert processed == 5
    assert len(received) == 5

    # Frame 2: Process 5 more
    processed = dispatcher.process_queue(max_events=5)
    assert processed == 5
    assert len(received) == 10

    # Frame 3: Process remaining
    processed = dispatcher.process_queue()
    assert processed == 10
    assert len(received) == 20

    # All events processed in order
    assert received == [f"event_{i}" for i in range(20)]


# ========== Base-class dispatch (wayfinder ticket 22) ==========


def test_base_class_subscriber_fires_on_leaf_dispatch(event_dispatcher):
    """A handler subscribed to a base class fires when a subclass is
    dispatched (walks type(event).__mro__, not just the exact type)."""
    from pyguara.physics.events import CollisionEvent, OnCollisionBegin
    from pyguara.common.types import Vector2

    received = []
    event_dispatcher.subscribe(CollisionEvent, lambda e: received.append(e))

    event = OnCollisionBegin(
        entity_a="a", entity_b="b", point=Vector2(0, 0), normal=Vector2(0, 1)
    )
    event_dispatcher.dispatch(event)

    assert received == [event]


def test_priority_governs_order_across_base_and_leaf_subscribers(event_dispatcher):
    """Call order follows priority alone across mixed base/leaf subscriptions,
    not which level (base class vs. exact type) each handler subscribed to."""

    order = []
    event_dispatcher.subscribe(
        CustomEvent, lambda e: order.append("leaf-low"), priority=1
    )
    event_dispatcher.subscribe(Event, lambda e: order.append("base-high"), priority=10)
    event_dispatcher.subscribe(
        CustomEvent, lambda e: order.append("leaf-mid"), priority=5
    )

    event_dispatcher.dispatch(CustomEvent(data=""))

    assert order == ["base-high", "leaf-mid", "leaf-low"]


def test_base_class_false_return_short_circuits_lower_priority_leaf_handler(
    event_dispatcher,
):
    """A higher-priority base-class handler returning False stops the whole
    merged pass -- including a lower-priority handler subscribed to the exact
    leaf type -- proving one short-circuiting pass, not per-type-level ones."""

    order = []

    def base_handler(e):
        order.append("base")
        return False

    event_dispatcher.subscribe(Event, base_handler, priority=10)
    event_dispatcher.subscribe(CustomEvent, lambda e: order.append("leaf"), priority=1)

    event_dispatcher.dispatch(CustomEvent(data=""))

    assert order == ["base"]


def test_history_disabled_by_default():
    """History is opt-in: a default-constructed dispatcher records nothing."""
    from pyguara.events.dispatcher import EventDispatcher

    dispatcher = EventDispatcher()
    dispatcher.dispatch(CustomEvent(data="a"))
    dispatcher.dispatch(CustomEvent(data="b"))

    assert dispatcher.get_history() == []


def test_history_enabled_records_bounded_deque():
    """enable_history=True records dispatched events, bounded (not unbounded
    list.pop(0) eviction) regardless."""
    from pyguara.events.dispatcher import EventDispatcher

    dispatcher = EventDispatcher(enable_history=True)

    events = [CustomEvent(data=str(i)) for i in range(5)]
    for event in events:
        dispatcher.dispatch(event)

    assert dispatcher.get_history() == events
    assert dispatcher.get_history(CustomEvent) == events


# -- Package import order (regression) --


def test_events_package_imports_before_log() -> None:
    """`pyguara.log` inherits the Event protocol at runtime, so log depends on
    events. If events also imported log at module scope the two would deadlock
    on first import -- which is exactly what happened the moment
    events/__init__.py started re-exporting the dispatcher. Import each
    package first in a clean interpreter to prove neither order breaks.
    """
    import subprocess
    import sys

    for first, second in (
        ("pyguara.events", "pyguara.log"),
        ("pyguara.log", "pyguara.events"),
    ):
        result = subprocess.run(
            [sys.executable, "-c", f"import {first}; import {second}"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"{first} then {second} failed:\n{result.stderr}"


def test_package_reexports_the_public_surface() -> None:
    import pyguara.events as events

    for name in ("EventDispatcher", "Event", "IEventDispatcher", "KeyDownEvent"):
        assert hasattr(events, name), name


# -- Event dataclasses --


def test_event_timestamps_default_to_now() -> None:
    import time as _time

    from pyguara.events.input import KeyDownEvent, MouseMotionEvent
    from pyguara.events.lifecycle import ApplicationStartEvent, QuitEvent
    from pyguara.events.window import WindowResizeEvent

    before = _time.time()
    events = [
        KeyDownEvent(key_code=32),
        MouseMotionEvent(1, 2, 3, 4),
        QuitEvent(),
        ApplicationStartEvent(),
        WindowResizeEvent(800, 600),
    ]
    after = _time.time()

    for event in events:
        assert before <= event.timestamp <= after, type(event).__name__


def test_an_explicit_zero_timestamp_is_honoured() -> None:
    """Every event class used `if self.timestamp == 0.0: self.timestamp =
    time.time()`, which made 0.0 impossible to express -- a real value was
    silently overwritten. field(default_factory=time.time) has no sentinel."""
    from pyguara.events.input import KeyDownEvent
    from pyguara.events.window import WindowResizeEvent

    assert KeyDownEvent(key_code=32, timestamp=0.0).timestamp == 0.0
    assert WindowResizeEvent(800, 600, timestamp=0.0).timestamp == 0.0


def test_key_events_share_a_base_so_one_handler_catches_both(event_dispatcher) -> None:
    from pyguara.events.input import KeyboardEvent, KeyDownEvent, KeyUpEvent

    seen = []
    event_dispatcher.subscribe(KeyboardEvent, lambda e: seen.append(type(e).__name__))

    event_dispatcher.dispatch(KeyDownEvent(key_code=1))
    event_dispatcher.dispatch(KeyUpEvent(key_code=1))

    assert seen == ["KeyDownEvent", "KeyUpEvent"]


# -- Filter errors follow the configured strategy --


def test_filter_exception_is_raised_under_raise_strategy() -> None:
    from unittest.mock import MagicMock

    dispatcher = EventDispatcher(
        logger=MagicMock(), error_strategy=ErrorHandlingStrategy.RAISE
    )

    def exploding_filter(_e):
        raise ValueError("filter blew up")

    dispatcher.subscribe(CustomEvent, lambda _e: None, filter_func=exploding_filter)

    with pytest.raises(ValueError, match="filter blew up"):
        dispatcher.dispatch(CustomEvent(data="x"))


def test_filter_exception_is_swallowed_under_ignore_strategy() -> None:
    """A filter is user code just like a handler, but its exceptions used to
    escape the error strategy entirely -- IGNORE still propagated them."""
    dispatcher = EventDispatcher(error_strategy=ErrorHandlingStrategy.IGNORE)

    def exploding_filter(_e):
        raise ValueError("filter blew up")

    ran = []
    dispatcher.subscribe(CustomEvent, lambda _e: None, filter_func=exploding_filter)
    dispatcher.subscribe(CustomEvent, lambda _e: ran.append(1))

    dispatcher.dispatch(CustomEvent(data="x"))

    assert ran == [1], "a failing filter must not stop later handlers"


def test_filter_exception_is_logged_and_skipped_under_log_strategy() -> None:
    from unittest.mock import MagicMock

    logger = MagicMock()
    dispatcher = EventDispatcher(
        logger=logger, error_strategy=ErrorHandlingStrategy.LOG
    )

    def exploding_filter(_e):
        raise ValueError("filter blew up")

    dispatcher.subscribe(CustomEvent, lambda _e: None, filter_func=exploding_filter)
    dispatcher.dispatch(CustomEvent(data="x"))

    logger.error.assert_called_once()
    assert "filter blew up" in logger.error.call_args[0][0]


# -- dispatch() reports consumption --


def test_dispatch_returns_true_when_every_handler_runs(event_dispatcher) -> None:
    event_dispatcher.subscribe(CustomEvent, lambda _e: None)
    assert event_dispatcher.dispatch(CustomEvent(data="x")) is True


def test_dispatch_returns_false_when_a_handler_consumes_the_event(
    event_dispatcher,
) -> None:
    """Returning False already stopped lower-priority handlers, but dispatch()
    returned None, so a caller could not tell a consumed event from a
    delivered one -- the case UI-over-game input handling needs."""
    event_dispatcher.subscribe(CustomEvent, lambda _e: False, priority=10)
    event_dispatcher.subscribe(CustomEvent, lambda _e: None, priority=0)

    assert event_dispatcher.dispatch(CustomEvent(data="x")) is False


def test_dispatch_returns_true_with_no_subscribers(event_dispatcher) -> None:
    assert event_dispatcher.dispatch(CustomEvent(data="x")) is True


def test_a_filtered_out_handler_does_not_count_as_consuming(event_dispatcher) -> None:
    event_dispatcher.subscribe(
        CustomEvent, lambda _e: False, filter_func=lambda _e: False
    )
    assert event_dispatcher.dispatch(CustomEvent(data="x")) is True


# -- Subscription bookkeeping --


def test_handler_cache_reflects_a_subscription_added_later(event_dispatcher) -> None:
    """dispatch() memoises the resolved handler list per event type; the cache
    must be dropped whenever the subscription set changes."""
    seen = []
    event_dispatcher.dispatch(CustomEvent(data="first"))

    event_dispatcher.subscribe(CustomEvent, lambda e: seen.append(e.data))
    event_dispatcher.dispatch(CustomEvent(data="second"))

    assert seen == ["second"]


def test_handler_cache_reflects_an_unsubscription(event_dispatcher) -> None:
    seen = []

    def handler(e):
        seen.append(e.data)

    event_dispatcher.subscribe(CustomEvent, handler)
    event_dispatcher.dispatch(CustomEvent(data="first"))

    event_dispatcher.unsubscribe(CustomEvent, handler)
    event_dispatcher.dispatch(CustomEvent(data="second"))

    assert seen == ["first"]


def test_handler_cache_reflects_a_base_class_subscription(event_dispatcher) -> None:
    """A later subscription on a *base* class must invalidate the cache for
    already-dispatched subclasses too."""
    from pyguara.events.input import KeyboardEvent, KeyDownEvent

    seen = []
    event_dispatcher.dispatch(KeyDownEvent(key_code=1))

    event_dispatcher.subscribe(KeyboardEvent, lambda _e: seen.append(1))
    event_dispatcher.dispatch(KeyDownEvent(key_code=1))

    assert seen == [1]


def test_clear_subscribers_for_one_type_leaves_others(event_dispatcher) -> None:
    from pyguara.events.lifecycle import QuitEvent

    seen = []
    event_dispatcher.subscribe(CustomEvent, lambda _e: seen.append("custom"))
    event_dispatcher.subscribe(QuitEvent, lambda _e: seen.append("quit"))

    event_dispatcher.clear_subscribers(CustomEvent)
    event_dispatcher.dispatch(CustomEvent(data="x"))
    event_dispatcher.dispatch(QuitEvent())

    assert seen == ["quit"]


def test_clear_subscribers_with_no_argument_clears_everything(event_dispatcher) -> None:
    seen = []
    event_dispatcher.subscribe(CustomEvent, lambda _e: seen.append(1))

    event_dispatcher.clear_subscribers()
    event_dispatcher.dispatch(CustomEvent(data="x"))

    assert seen == []


def test_unsubscribing_an_unknown_handler_is_a_noop(event_dispatcher) -> None:
    event_dispatcher.unsubscribe(CustomEvent, lambda _e: None)


def test_the_same_handler_subscribed_twice_runs_twice(event_dispatcher) -> None:
    """Deliberate: a callable may be registered at two priorities or with two
    filters, so subscriptions are distinct records, not deduplicated by
    callback the way EntityManager's removal hook is."""
    calls = []

    def handler(_e):
        calls.append(1)

    event_dispatcher.subscribe(CustomEvent, handler, priority=10)
    event_dispatcher.subscribe(CustomEvent, handler, priority=0)
    event_dispatcher.dispatch(CustomEvent(data="x"))

    assert len(calls) == 2


def test_unsubscribe_removes_every_registration_of_a_handler(event_dispatcher) -> None:
    calls = []

    def handler(_e):
        calls.append(1)

    event_dispatcher.subscribe(CustomEvent, handler, priority=10)
    event_dispatcher.subscribe(CustomEvent, handler, priority=0)
    event_dispatcher.unsubscribe(CustomEvent, handler)
    event_dispatcher.dispatch(CustomEvent(data="x"))

    assert calls == []


def test_the_handler_list_is_snapshotted_for_the_duration_of_a_dispatch(
    event_dispatcher,
) -> None:
    """A handler that unsubscribes another still lets that one run for the
    dispatch already in flight; the change takes effect on the next one."""
    order = []

    def second(_e):
        order.append("second")

    def first(_e):
        order.append("first")
        event_dispatcher.unsubscribe(CustomEvent, second)

    event_dispatcher.subscribe(CustomEvent, first, priority=10)
    event_dispatcher.subscribe(CustomEvent, second, priority=0)

    event_dispatcher.dispatch(CustomEvent(data="x"))
    event_dispatcher.dispatch(CustomEvent(data="y"))

    assert order == ["first", "second", "first"]


# -- Queue --


def test_queue_event_is_safe_from_background_threads() -> None:
    """queue_event() is the documented thread-safe entry point; prove it under
    real contention rather than trusting queue.Queue by inspection."""
    import threading

    dispatcher = EventDispatcher()
    received = []
    dispatcher.subscribe(CustomEvent, lambda e: received.append(e.data))

    def producer(worker: int) -> None:
        for i in range(50):
            dispatcher.queue_event(CustomEvent(data=f"{worker}-{i}"))

    threads = [threading.Thread(target=producer, args=(w,)) for w in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert dispatcher.process_queue() == 200
    assert len(set(received)) == 200


def test_events_queued_by_a_handler_wait_for_the_next_drain() -> None:
    dispatcher = EventDispatcher()
    seen = []

    def handler(e):
        seen.append(e.data)
        if e.data == "first":
            dispatcher.queue_event(CustomEvent(data="second"))

    dispatcher.subscribe(CustomEvent, handler)
    dispatcher.queue_event(CustomEvent(data="first"))

    assert dispatcher.process_queue() == 1
    assert seen == ["first"]
    assert dispatcher.process_queue() == 1
    assert seen == ["first", "second"]


# -- History --


def test_history_can_be_filtered_by_type() -> None:
    from pyguara.events.lifecycle import QuitEvent

    dispatcher = EventDispatcher(enable_history=True)
    dispatcher.dispatch(CustomEvent(data="x"))
    dispatcher.dispatch(QuitEvent())

    assert len(dispatcher.get_history()) == 2
    assert len(dispatcher.get_history(QuitEvent)) == 1


def test_history_size_is_configurable() -> None:
    dispatcher = EventDispatcher(enable_history=True, max_history_size=3)
    for i in range(10):
        dispatcher.dispatch(CustomEvent(data=str(i)))

    history = dispatcher.get_history()
    assert len(history) == 3
    assert [e.data for e in history] == ["7", "8", "9"]


def test_get_history_returns_a_snapshot_not_the_live_deque() -> None:
    dispatcher = EventDispatcher(enable_history=True)
    dispatcher.dispatch(CustomEvent(data="x"))

    dispatcher.get_history().clear()

    assert len(dispatcher.get_history()) == 1
