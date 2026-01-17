from dataclasses import dataclass
from typing import Any
from pyguara.events.protocols import Event


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
